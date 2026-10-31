"""PostGIS queries. All queries are parameterized through SQLAlchemy."""
import json
import uuid

from geoalchemy2 import Geography
from geoalchemy2.functions import ST_Covers, ST_Distance, ST_DWithin, ST_GeomFromGeoJSON, ST_IsValid, ST_SetSRID, ST_MakePoint
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from app.models import Jurisdiction, SensitiveLocation


def point_wkt(lat: float, lng: float) -> str:
    return f"SRID=4326;POINT({lng} {lat})"


def make_point(lat: float, lng: float):
    return ST_SetSRID(ST_MakePoint(lng, lat), 4326)


def containing_jurisdictions(db: Session, lat: float, lng: float) -> list[Jurisdiction]:
    stmt = (
        select(Jurisdiction)
        .where(Jurisdiction.active.is_(True))
        .where(ST_Covers(Jurisdiction.boundary, make_point(lat, lng)))
        .order_by(Jurisdiction.name)
    )
    return list(db.scalars(stmt))


def any_active_jurisdiction(db: Session) -> bool:
    return db.scalar(select(func.count()).select_from(Jurisdiction).where(Jurisdiction.active.is_(True))) > 0


def matching_sensitive_locations(db: Session, lat: float, lng: float) -> list[tuple[SensitiveLocation, float]]:
    pt = cast(make_point(lat, lng), Geography)
    dist = ST_Distance(SensitiveLocation.point, pt)
    stmt = (
        select(SensitiveLocation, dist)
        .where(SensitiveLocation.active.is_(True))
        .where(ST_DWithin(SensitiveLocation.point, pt, SensitiveLocation.radius_m))
        .order_by(SensitiveLocation.sensitivity_score.desc())
    )
    return [(row[0], float(row[1])) for row in db.execute(stmt)]


def any_sensitive_location(db: Session) -> bool:
    return db.scalar(select(func.count()).select_from(SensitiveLocation).where(SensitiveLocation.active.is_(True))) > 0


class InvalidGeometry(ValueError):
    pass


def geojson_to_geometry(db: Session, geojson: dict):
    """Validate a GeoJSON Polygon/MultiPolygon with PostGIS and return a geometry expression."""
    if not isinstance(geojson, dict) or geojson.get("type") not in ("Polygon", "MultiPolygon"):
        raise InvalidGeometry("Boundary must be a GeoJSON Polygon or MultiPolygon geometry.")
    text = json.dumps(geojson)
    try:
        valid = db.scalar(select(ST_IsValid(ST_GeomFromGeoJSON(text))))
    except Exception as exc:  # malformed GeoJSON
        db.rollback()
        raise InvalidGeometry("Boundary GeoJSON could not be parsed.") from exc
    if not valid:
        raise InvalidGeometry("Boundary polygon is not valid (e.g. self-intersecting).")
    return ST_SetSRID(ST_GeomFromGeoJSON(text), 4326)


def geometry_as_geojson(db: Session, jurisdiction_id: uuid.UUID) -> dict | None:
    raw = db.scalar(select(func.ST_AsGeoJSON(Jurisdiction.boundary)).where(Jurisdiction.id == jurisdiction_id))
    return json.loads(raw) if raw else None
