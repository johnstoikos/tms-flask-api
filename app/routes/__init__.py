from flask import Flask

def register_blueprints(app: Flask):
    """Καταχωρεί όλα τα Blueprints της εφαρμογής στο κεντρικό Flask app."""
    from .health import health_bp
    from .templates import templates_bp
    from .statistics import statistics_bp 
    from .terminals import terminals_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(templates_bp)
    app.register_blueprint(statistics_bp)   
    app.register_blueprint(terminals_bp)