import traceback

from flask import Flask, render_template, g, request
from blueprint import (
    customer_blueprint,
    admin_user_blueprint,
    batch_blueprint,
    api_blueprint,
    patch_blueprint,
)
from dotenv import load_dotenv
from datetime import timedelta, datetime
from service.slack_service import SlackService


load_dotenv()

app = Flask(__name__)

app.config.from_mapping(SECRET_KEY="aroot")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=365)

app.register_blueprint(customer_blueprint.bp)
app.register_blueprint(admin_user_blueprint.bp)
app.register_blueprint(batch_blueprint.bp)
app.register_blueprint(api_blueprint.bp)
app.register_blueprint(patch_blueprint.bp)


# Custom Jinja2 filter for converting UTC to JST
@app.template_filter('jst')
def utc_to_jst(utc_datetime):
    """Convert UTC datetime to JST (Japan Standard Time)"""
    if utc_datetime is None:
        return ""
    
    if isinstance(utc_datetime, str):
        try:
            # Try to parse the string as datetime
            utc_datetime = datetime.fromisoformat(utc_datetime.replace('Z', '+00:00'))
        except ValueError:
            return utc_datetime  # Return original string if parsing fails
    
    if isinstance(utc_datetime, datetime):
        # Add 9 hours to convert UTC to JST
        jst_datetime = utc_datetime + timedelta(hours=9)
        return jst_datetime.strftime('%Y/%m/%d %H:%M')
    
    return str(utc_datetime)


@app.teardown_appcontext
def close_redis(exception):
    redis_client = g.pop("redis", None)
    if redis_client is not None:
        redis_client.close()


@app.errorhandler(404)
def handle_404(error):
    return render_template("404.html"), 404


@app.errorhandler(429)
def handle_rate_limit(error):
    return render_template(
        "errors.html",
        errors="リクエスト数が上限に達しました。しばらく時間をおいてから再試行してください。"
    ), 429


@app.errorhandler(Exception)
def handle_exception(error):
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    stack_trace = traceback.format_exc()
    msg = f"""```● Error: {error}
    ● method: {request.method}
    ● url: {request.url}
    ● client IP: {client_ip}

    {stack_trace}```"""
    SlackService().send_alert(msg)
    return render_template("errors.html", errors=error)


@app.route("/terms")
def terms():
    return render_template("etc/terms.html")


@app.route("/privacy")
def privacy():
    return render_template("etc/privacy.html")


@app.route("/releases")
def releases():
    return render_template("etc/releases.html")


@app.route("/flask-health-check")
def flask_health_check():
    return "success"


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
