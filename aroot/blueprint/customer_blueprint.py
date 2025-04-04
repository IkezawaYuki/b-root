import functools
import traceback
from flask import (
    Blueprint,
    flash,
    session,
    redirect,
    render_template,
    request,
    url_for,
    jsonify,
)

from datetime import timedelta, datetime

from flask.sessions import SessionMixin
from typing_extensions import Optional

from util.const import DashboardStatus, EXPIRED, NOT_CONNECTED

from repository.posts_repository import PostsRepository
from repository.unit_of_work import UnitOfWork
from repository.customers_repository import CustomersRepository
from service.customers_service import (
    CustomersService,
    CustomerNotFoundError,
    CustomerAuthError,
)
from service.openai_service import OpenAIService
from service.posts_service import PostsService
from service.meta_service import MetaService, MetaApiError, MetaAccountNotFoundError
from service.redis_client import get_redis
from service.slack_service import SlackService
from service.wordpress_service import WordpressService, WordpressAuthError
from domain.instagram_media import convert_to_json


bp = Blueprint("customer", __name__)


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        customer_id = session.get("customer_id")
        if customer_id is None:
            return redirect(url_for("customer.login"))
        return view(**kwargs)

    return wrapped_view


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        if not email or not password:
            error = "メールアドレスかパスワードが間違っています"
        else:
            try:
                with UnitOfWork() as unit_of_work:
                    customer_repo = CustomersRepository(unit_of_work.session)
                    customer_service = CustomersService(customer_repo)
                    customer = customer_service.get_customer_by_email(email)
                    customer.check_password_hash(password)
                    session["customer_id"] = customer.id
                    session.permanent = True
                    unit_of_work.commit()
                    return redirect(url_for("customer.index"))
            except CustomerNotFoundError:
                error = "メールアドレスかパスワードが間違っています"
            except CustomerAuthError:
                error = "メールアドレスかパスワードが間違っています"
        flash(message=error, category="warning")
    return render_template("customer/login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("customer.login"))


@bp.route("/")
@login_required
def index():
    customer_id = session.get("customer_id")
    with UnitOfWork() as unit_of_work:
        customer_repo = CustomersRepository(unit_of_work.session)
        customers_service = CustomersService(customer_repo)
        customer = customers_service.get_customer_by_id(customer_id)
        posts_repo = PostsRepository(unit_of_work.session)
        posts_service = PostsService(posts_repo)
        posts = posts_service.find_by_customer_id(customer_id)
    dashboard_status = session.pop("dashboard_status", None)
    if dashboard_status is None:
        if customer.instagram_token_status == EXPIRED:
            dashboard_status = DashboardStatus.TOKEN_EXPIRED.value
        elif customer.instagram_token_status == NOT_CONNECTED:
            dashboard_status = DashboardStatus.AUTH_PENDING.value
        else:
            dashboard_status = DashboardStatus.HEALTHY.value
    return render_template(
        "customer/index.html",
        customer=customer,
        posts=posts,
        dashboard_status=dashboard_status,
    )


@bp.route("/start_date", methods=("POST",))
@login_required
def start_date():
    customer_id = session.get("customer_id")
    new_start_date = request.form.get("start_date")
    if new_start_date:
        utc_time = datetime.strptime(new_start_date, "%Y-%m-%dT%H:%M:%S") - timedelta(
            hours=9
        )
        with UnitOfWork() as unit_of_work:
            customer_repo = CustomersRepository(unit_of_work.session)
            customer_repo.update(customer_id, start_date=utc_time)
            unit_of_work.commit()
            flash(message="日時を更新しました", category="success")
            set_dashboard_status(session, DashboardStatus.MOD_START_DATE.value)
    return redirect(url_for("customer.index"))


@bp.route("/facebook/auth", methods=("POST",))
@login_required
def facebook_auth():
    customer_id = session.get("customer_id")
    access_token = request.form["access_token"]
    try:
        with UnitOfWork() as unit_of_work:
            customers_repo = CustomersRepository(unit_of_work.session)
            customer_service = CustomersService(customers_repo)
            customer = customer_service.get_customer_by_id(customer_id)
            meta_service = MetaService()
            long_token = meta_service.get_long_term_token(access_token)
            instagram = meta_service.get_instagram_account(access_token)
            customer_service.update_customer_after_login(
                customer_id, long_token, instagram["id"], instagram["username"]
            )
            wordpress_service = WordpressService(
                customer.wordpress_url, customer.delete_hash, customer.name
            )
            wordpress_service.ping()
            unit_of_work.commit()
            flash(
                message=f"インスタグラムアカウントとの連携に成功しました",
                category="success",
            )
            set_dashboard_status(session, DashboardStatus.AUTH_SUCCESS.value)
    except MetaAccountNotFoundError as e:
        send_alert(e)
        flash(
            message=f"Instagramアカウントの取得に失敗しました。設定を確認してください: {str(e)}",
            category="alert",
        )
        set_dashboard_status(session, DashboardStatus.AUTH_ERROR_INSTAGRAM.value)
    except WordpressAuthError as e:
        send_alert(e)
        flash(
            message=f"Wordpressとの疎通に失敗しました。管理者にご連絡ください: {str(e)}",
            category="alert",
        )
        set_dashboard_status(session, DashboardStatus.AUTH_ERROR_WORDPRESS.value)
    except MetaApiError as e:
        send_alert(e)
        flash(
            message=f"Instagramアカウントの取得に失敗しました。設定を確認してください: {str(e)}",
            category="warning",
        )
        set_dashboard_status(session, DashboardStatus.AUTH_ERROR_INSTAGRAM.value)
    return redirect(url_for("customer.index"))


def send_alert(e: Exception):
    err_txt = str(e)
    stack_trace = traceback.format_exc()
    msg = f"```{err_txt}\n{stack_trace}```"
    SlackService().send_alert(msg)


@bp.route("/instagram", methods=("POST",))
@login_required
def get_instagram():
    try:
        with UnitOfWork() as unit_of_work:
            customers_repo = CustomersRepository(unit_of_work.session)
            customer_service = CustomersService(customers_repo)
            customer_id = session.get("customer_id")
            customer = customer_service.get_customer_by_id(customer_id)
            posts_repo = PostsRepository(unit_of_work.session)
            posts_service = PostsService(posts_repo)
            meta_service = MetaService()
            media_id_list = meta_service.get_media_list(
                customer.facebook_token, customer.instagram_business_account_id
            )
            linked_post = posts_service.find_by_customer_id(customer.id)
            targets = posts_service.abstract_targets(
                media_id_list, linked_post, customer.start_date
            )
            unit_of_work.commit()
            json_data = convert_to_json(targets)
            return jsonify(json_data)
    except MetaApiError as e:
        return jsonify({"error": str(e)})


@bp.route("/post/wordpress", methods=("POST",))
@login_required
def post_wordpress():
    try:
        with UnitOfWork() as unit_of_work:
            customers_repo = CustomersRepository(unit_of_work.session)
            customer_service = CustomersService(customers_repo)
            posts_repo = PostsRepository(unit_of_work.session)
            posts_service = PostsService(posts_repo)
            customer_id = session.get("customer_id")
            customer = customer_service.get_customer_by_id(customer_id)
            wordpress_service = WordpressService(
                customer.wordpress_url, customer.delete_hash, customer.name
            )
            meta_service = MetaService()
            media_id_list = meta_service.get_media_list(
                customer.facebook_token, customer.instagram_business_account_id
            )
            linked_post = posts_service.find_by_customer_id(customer.id)
            targets = posts_service.abstract_targets(
                media_id_list, linked_post, customer.start_date
            )
            result = wordpress_service.posts(targets)
            posts_service.save_posts(result, customer_id)
            unit_of_work.commit()
            return jsonify({"status": "success"})
    except Exception as e:
        err_txt = str(e)
        stack_trace = traceback.format_exc()
        msg = f"```{customer.name}\n\n{err_txt}\n\n{stack_trace}```"
        SlackService().send_alert(msg)
        return jsonify({"error": str(e)})


@bp.route("/maika/dashboard", methods=("POST",))
def maika_dashboard():
    customer_id = request.json.get("customer_id")
    dashboard_status_str = request.json.get("dashboard_status")
    dashboard_status = DashboardStatus(dashboard_status_str)
    openai_client = OpenAIService()
    ai_message = openai_client.generate_message(customer_id, dashboard_status)
    return jsonify({"status": "success", "message": ai_message})


@bp.route("/relink", methods=("GET",))
@login_required
def relink():
    return render_template("customer/relink.html")


def get_dashboard_status(session_mixin: SessionMixin) -> Optional[DashboardStatus]:
    dashboard_status = session_mixin.get("dashboard_status")
    if dashboard_status is not None:
        timestamp = session_mixin.get("dashboard_status_timestamp")
        if timestamp is not None:
            expiration_time = timestamp + timedelta(minutes=60)
            if datetime.now() < expiration_time:
                return DashboardStatus(dashboard_status)
    session_mixin.pop("dashboard_status", None)
    session_mixin.pop("dashboard_status_timestamp", None)
    return None


def set_dashboard_status(
    session_mixin: SessionMixin, dashboard_status: DashboardStatus
):
    session_mixin["dashboard_status"] = dashboard_status
    session_mixin["dashboard_status_timestamp"] = datetime.now()
