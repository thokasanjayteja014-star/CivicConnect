"""Stable, machine-readable API errors (spec section 8).

Every error response has: error_code, message, details (optional), request_id.
"""
from typing import Any


class ApiError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details


# Catalogue of the spec's error cases. Keyed by error_code.
_CATALOGUE: dict[str, tuple[int, str]] = {
    "EMPTY_COMPLAINT": (422, "Please provide a complaint description or supported media before continuing."),
    "DESCRIPTION_TOO_SHORT": (422, "Please provide a more detailed description of the issue."),
    "DESCRIPTION_TOO_LONG": (422, "Your description exceeds the 3000-character limit."),
    "INVALID_COORDINATES": (422, "The selected location is invalid. Please choose a valid location."),
    "LOCATION_UNAVAILABLE": (400, "We could not access your location. Please select the issue location on the map."),
    "UNSUPPORTED_MEDIA_TYPE": (415, "This file format is not supported. Please upload a supported image, audio or video file."),
    "FILE_TOO_LARGE": (413, "The selected file exceeds the permitted upload size."),
    "TOO_MANY_IMAGES": (422, "You can upload a maximum of 5 images per complaint."),
    "TOO_MANY_MEDIA": (422, "Too many files of this type were attached to the complaint."),
    "MEDIA_DURATION_EXCEEDED": (422, "The media duration exceeds the permitted limit."),
    "CORRUPT_MEDIA": (422, "We could not read this file. Please upload a valid file."),
    "AI_NOT_CONFIGURED": (503, "AI analysis is currently unavailable. You can continue with manual complaint details."),
    "AI_NOT_IMPLEMENTED": (503, "AI analysis is currently unavailable. You can continue with manual complaint details."),
    "AI_TIMEOUT": (504, "Complaint analysis took too long. Please retry or continue manually."),
    "AI_PROVIDER_FAILURE": (502, "We could not analyze your complaint at this time."),
    "AI_INVALID_OUTPUT": (502, "The analysis result could not be validated. Please retry or continue manually."),
    "AI_TRANSCRIPTION_FAILED": (502, "We could not transcribe the audio. Please retry or provide a written description."),
    "UNAUTHENTICATED": (401, "Please log in to continue."),
    "FORBIDDEN": (403, "You do not have permission to perform this action."),
    "COMPLAINT_NOT_FOUND": (404, "The requested complaint could not be found."),
    "MEDIA_NOT_AVAILABLE": (404, "This media resource is not available to your account."),
    "INVALID_ASSIGNMENT": (422, "The selected officer is not eligible for this assignment."),
    "INVALID_STATUS_TRANSITION": (409, "This complaint cannot be moved to the selected status."),
    "REASON_REQUIRED": (422, "Please provide a reason before completing this action."),
    "ALREADY_UPDATED": (409, "This complaint has already been updated."),
    "DUPLICATE_SUBMISSION": (409, "This complaint submission has already been processed."),
    "REOPEN_NOT_ALLOWED": (409, "This complaint cannot currently be reopened."),
    "DATABASE_UNAVAILABLE": (503, "CivicConnect is temporarily unable to save your complaint. Please try again."),
    "GEOCODER_UNAVAILABLE": (503, "Address search is unavailable right now. Please pick the location on the map."),
    "MEDIA_STORAGE_FAILURE": (503, "We could not upload your media. Please retry the upload."),
    "CONCURRENT_UPDATE": (409, "This complaint was updated by another user. Refresh the page before continuing."),
    "EVIDENCE_REQUIRED": (409, "At least one resolution evidence record is required before this action."),
    "VALIDATION_ERROR": (422, "Some fields are invalid. Please review and try again."),
    "NOT_FOUND": (404, "The requested resource could not be found."),
    "CONFLICT": (409, "The request conflicts with the current state of the resource."),
    "INVALID_CREDENTIALS": (401, "The email or password is incorrect."),
    "ACCOUNT_DISABLED": (403, "This account is not active."),
    "EMAIL_IN_USE": (409, "An account with this email already exists."),
    "RATE_LIMITED": (429, "Too many requests. Please wait a moment and try again."),
    "INTERNAL_ERROR": (500, "Something went wrong on our side. Please try again."),
}


def err(code: str, message: str | None = None, details: Any = None, status_code: int | None = None) -> ApiError:
    status, default_message = _CATALOGUE.get(code, (400, code))
    return ApiError(status_code or status, code, message or default_message, details)
