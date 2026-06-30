from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.backends.signals import connection_created
from django.db.models.signals import post_migrate
from django.dispatch import receiver


SEED_CODES = [
    ("DOC_SRS", "사용자 요구사항 정의서", ""),
    ("DOC_ITF", "사용자 인터페이스 설계서", ""),
    ("DOC_ARCH", "아키텍처 설계서", ""),
    ("DOC_ERD", "엔티티 관계 모형 설계서", ""),
    ("DOC_DB", "데이터베이스 설계서", ""),
    ("DOC_TS", "통합 시험 시나리오", ""),
    ("FILE_MEETING", "회의록", "문서관리 > 회의록 파일"),
    ("FILE_RFP", "사업제안서(RFP)", "문서관리 > 사업제안서"),
    (
        "FILE_REQ_DOC_JSON",
        "사용자 요구사항 정의서 json",
        "생성된 요구사항 정의 UI와 별도로 관리되는 최종 json 문서",
    ),
    ("PRGRS_PENDING", "생성 대기", "문서 생성 작업 대기 상태"),
    ("PRGRS_PROCESSING", "생성 중", "문서 생성 작업 진행 상태"),
    ("PRGRS_COMPLETED", "생성 완료", "문서 생성 작업 완료 상태"),
    ("PRGRS_FAILED", "생성 실패", "문서 생성 작업 실패 상태"),
    ("ROLE_MEMBER", "멤버", "프로젝트 할당 권한"),
    ("ROLE_MANAGER", "관리자", "프로젝트 관리자 권한"),
    ("APRV_REQ", "승인 대기", "산출물 승인 요청 상태"),
    ("APRV_COM", "승인 완료", "산출물 승인 완료 상태"),
    ("APRV_RJT", "반려", "산출물 승인 반려 상태"),
]
def _ensure_admin_user():
    try:
        User = get_user_model()
        admin = User.objects.filter(user_id="admin").first()
        if admin is None:
            next_sn = (User.objects.order_by("-sn").values_list("sn", flat=True).first() or 0) + 1
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO tbl_user (
                        user_sn,
                        user_id,
                        user_pswd,
                        user_nm,
                        dept_nm,
                        jbgd_nm,
                        sys_mngr_yn,
                        tmpr_pswd_yn,
                        use_yn,
                        crt_dt,
                        creatr_sn,
                        mdfcn_dt,
                        mdfr_sn
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        CURRENT_TIMESTAMP, %s, CURRENT_TIMESTAMP, %s
                    )
                    """,
                    [
                        next_sn,
                        "admin",
                        make_password("abc1234"),
                        "관리자",
                        "시스템",
                        "관리자",
                        "Y",
                        "N",
                        "Y",
                        next_sn,
                        next_sn,
                    ],
                )
            admin = User.objects.get(sn=next_sn)

        update_fields = []
        if admin.sys_mngr_yn != "Y":
            admin.sys_mngr_yn = "Y"
            update_fields.append("sys_mngr_yn")
        if admin.use_yn != "Y":
            admin.use_yn = "Y"
            update_fields.append("use_yn")
        if admin.created_by_id is None:
            admin.created_by = admin
            update_fields.append("created_by")
        if admin.updated_by_id is None:
            admin.updated_by = admin
            update_fields.append("updated_by")
        if update_fields:
            admin.save(update_fields=update_fields)
        return admin
    except Exception:
        return None


def ensure_initial_reference_data():
    try:
        existing_tables = set(connection.introspection.table_names())
    except Exception:
        return

    if not {"tbl_user", "tbl_code"}.issubset(existing_tables):
        return

    Code = django_apps.get_model("common", "Code")
    admin = _ensure_admin_user()
    if admin is None:
        return

    try:
        for code, name, remarks in SEED_CODES:
            Code.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "remarks": remarks,
                    "created_by": admin,
                    "updated_by": admin,
                },
            )
    except Exception:
        return


@receiver(post_migrate, dispatch_uid="common.seed_initial_reference_data")
def seed_initial_reference_data(sender, app_config, **kwargs):
    if app_config.label != "common":
        return
    ensure_initial_reference_data()


@receiver(connection_created, dispatch_uid="common.sqlite_memory_journal")
def configure_sqlite_connection(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return

    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode=MEMORY;")
        cursor.execute("PRAGMA synchronous=OFF;")
        cursor.execute("PRAGMA temp_store=MEMORY;")
