"""Application errors with stable codes, mapped to clean JSON responses."""


class AppError(Exception):
    """An error that is safe (and useful) to show to the user."""

    def __init__(self, code: str, message: str, status: int = 400, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details

    def to_dict(self):
        payload = {"code": self.code, "message": self.message}
        if self.details is not None:
            payload["details"] = self.details
        return {"error": payload}


def register_error_handlers(app):
    from flask import jsonify

    import logging

    logger = logging.getLogger("docwiz")

    @app.errorhandler(AppError)
    def handle_app_error(err: AppError):
        logger.warning("AppError %s (%s): %s", err.code, err.status, err.message)
        return jsonify(err.to_dict()), err.status

    @app.errorhandler(404)
    def handle_404(_err):
        return jsonify({"error": {"code": "not_found", "message": "Unknown endpoint."}}), 404

    @app.errorhandler(405)
    def handle_405(_err):
        return jsonify({"error": {"code": "method_not_allowed", "message": "Unsupported method for this endpoint."}}), 405

    @app.errorhandler(413)
    def handle_413(_err):
        return (
            jsonify(
                {
                    "error": {
                        "code": "file_too_large",
                        "message": "Upload is larger than the configured size limit.",
                    }
                }
            ),
            413,
        )

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        # Full traceback goes to the server log only — never to the browser.
        logger.exception("Unhandled server error: %s", err)
        return (
            jsonify(
                {
                    "error": {
                        "code": "internal_error",
                        "message": "Something went wrong on the server. Check the DocWiz console for details.",
                    }
                }
            ),
            500,
        )
