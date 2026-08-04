import json

from fastapi.testclient import TestClient

from api.app import create_app
from emailing.store import EmailStore


def test_create_and_start_email_campaign(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)

    hunt = {
        "status": "completed",
        "result": {
            "email_sequences": [
                {
                    "lead": {"company_name": "Acme", "website": "https://acme.com"},
                    "locale": "en_US",
                    "review_summary": {"status": "approved", "score": 92},
                    "auto_send_eligible": True,
                    "generation_mode": "template_pool",
                    "template_id": "tpl_123",
                    "template_group": "en_US|decision_maker_verified|general",
                    "template_usage_index": 1,
                    "template_max_send_count": 100,
                    "target": {
                        "target_email": "buyer@acme.com",
                        "target_name": "Jane",
                        "target_title": "Purchasing Manager",
                        "target_type": "decision_maker_verified",
                    },
                    "targets": [
                        {
                            "target_email": "buyer@acme.com",
                            "target_name": "Jane",
                            "target_title": "Purchasing Manager",
                            "target_type": "decision_maker_verified",
                        },
                        {
                            "target_email": "sales@acme.com",
                            "target_name": "",
                            "target_title": "",
                            "target_type": "generic_company_email",
                        },
                    ],
                    "emails": [
                        {"sequence_number": 1, "email_type": "company_intro", "subject": "Hi", "body_text": "A", "suggested_send_day": 0},
                        {"sequence_number": 2, "email_type": "product_showcase", "subject": "Hi2", "body_text": "B", "suggested_send_day": 3},
                        {"sequence_number": 3, "email_type": "partnership_proposal", "subject": "Hi3", "body_text": "C", "suggested_send_day": 7},
                    ],
                }
            ]
        },
    }
    saved = {}

    monkeypatch.setattr("api.email_routes.load_hunt", lambda hunt_id: hunt)
    monkeypatch.setattr("api.email_routes.save_hunt", lambda hunt_id, data: saved.update({hunt_id: data}))
    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(tmp_path / "email.db"),
        "email_provider_type": "smtp",
        "email_from_name": "JPS One",
        "email_from_address": "sales@example.com",
        "email_reply_to": "sales@example.com",
        "email_smtp_host": "smtp.example.com",
        "email_smtp_port": 587,
        "email_smtp_username": "sales@example.com",
        "email_smtp_password": "secret",
        "email_smtp_last_test_at": "2026-04-04T10:00:00Z",
        "email_imap_host": "",
        "email_imap_port": 993,
        "email_imap_username": "",
        "email_imap_password": "",
        "email_use_tls": True,
        "email_daily_send_limit": 50,
        "email_hourly_send_limit": 10,
        "email_language_mode": "auto_by_region",
        "email_default_language": "en",
        "email_fallback_language": "en",
        "email_tone": "professional",
        "email_step1_delay_days": 0,
        "email_step2_delay_days": 3,
        "email_step3_delay_days": 3,
        "email_min_fit_score_to_send": 0.6,
        "email_min_contactability_score_to_send": 0.45,
    })())

    res = client.post("/api/v1/hunts/hunt_1/email-campaigns", json={"name": "Test Campaign"})
    assert res.status_code == 200
    campaign_id = res.json()["campaign_id"]
    assert res.json()["sequence_count"] == 2

    res = client.post(f"/api/v1/email-campaigns/{campaign_id}/start")
    assert res.status_code == 200
    assert res.json()["status"] == "active"

    res = client.get("/api/v1/hunts/hunt_1/email-campaigns")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["template_summary"][0]["template_id"] == "tpl_123"
    assert saved["hunt_1"]["result"]["email_campaign_summary"]["template_summary"][0]["template_id"] == "tpl_123"


def test_create_campaign_skips_blocked_template(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)

    hunt = {
        "status": "completed",
        "result": {
            "email_sequences": [
                {
                    "lead": {"company_name": "Blocked", "website": "https://blocked.com"},
                    "locale": "en_US",
                    "generation_mode": "template_pool",
                    "template_id": "tpl_bad",
                    "template_group": "en_US|decision_maker_verified|general",
                    "template_usage_index": 1,
                    "template_max_send_count": 100,
                    "template_performance": {"status": "underperforming"},
                    "target": {
                        "target_email": "buyer@blocked.com",
                        "target_name": "Jane",
                        "target_title": "Purchasing Manager",
                        "target_type": "decision_maker_verified",
                    },
                    "emails": [
                        {"sequence_number": 1, "email_type": "company_intro", "subject": "Hi", "body_text": "A", "suggested_send_day": 0},
                    ],
                }
            ]
        },
    }

    monkeypatch.setattr("api.email_routes.load_hunt", lambda hunt_id: hunt)
    monkeypatch.setattr("api.email_routes.save_hunt", lambda hunt_id, data: None)
    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(tmp_path / "email.db"),
        "email_provider_type": "smtp",
        "email_from_name": "JPS One",
        "email_from_address": "sales@example.com",
        "email_reply_to": "sales@example.com",
        "email_smtp_host": "smtp.example.com",
        "email_smtp_port": 587,
        "email_smtp_username": "sales@example.com",
        "email_smtp_password": "secret",
        "email_smtp_last_test_at": "2026-04-04T10:00:00Z",
        "email_imap_host": "",
        "email_imap_port": 993,
        "email_imap_username": "",
        "email_imap_password": "",
        "email_use_tls": True,
        "email_daily_send_limit": 50,
        "email_hourly_send_limit": 10,
        "email_language_mode": "auto_by_region",
        "email_default_language": "en",
        "email_fallback_language": "en",
        "email_tone": "professional",
        "email_step1_delay_days": 0,
        "email_step2_delay_days": 3,
        "email_step3_delay_days": 3,
        "email_min_fit_score_to_send": 0.6,
        "email_min_contactability_score_to_send": 0.45,
    })())

    res = client.post("/api/v1/hunts/hunt_1/email-campaigns", json={"name": "Blocked Campaign"})
    assert res.status_code == 200
    assert res.json()["sequence_count"] == 0


def test_create_campaign_skips_unapproved_sequences(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)

    hunt = {
        "status": "completed",
        "result": {
            "email_sequences": [
                {
                    "lead": {"company_name": "Needs Review", "website": "https://review.com"},
                    "locale": "en_US",
                    "review_summary": {"status": "needs_review", "score": 61},
                    "auto_send_eligible": False,
                    "target": {
                        "target_email": "buyer@review.com",
                        "target_name": "Jane",
                        "target_title": "Purchasing Manager",
                        "target_type": "decision_maker_verified",
                    },
                    "emails": [
                        {"sequence_number": 1, "email_type": "company_intro", "subject": "Hi", "body_text": "A", "suggested_send_day": 0},
                    ],
                },
                {
                    "lead": {"company_name": "Approved", "website": "https://approved.com"},
                    "locale": "en_US",
                    "review_summary": {"status": "approved", "score": 90},
                    "auto_send_eligible": True,
                    "target": {
                        "target_email": "buyer@approved.com",
                        "target_name": "John",
                        "target_title": "Purchasing Manager",
                        "target_type": "decision_maker_verified",
                    },
                    "emails": [
                        {"sequence_number": 1, "email_type": "company_intro", "subject": "Hi", "body_text": "A", "suggested_send_day": 0},
                    ],
                }
            ]
        },
    }

    monkeypatch.setattr("api.email_routes.load_hunt", lambda hunt_id: hunt)
    monkeypatch.setattr("api.email_routes.save_hunt", lambda hunt_id, data: None)
    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(tmp_path / "email.db"),
        "email_provider_type": "smtp",
        "email_from_name": "JPS One",
        "email_from_address": "sales@example.com",
        "email_reply_to": "sales@example.com",
        "email_smtp_host": "smtp.example.com",
        "email_smtp_port": 587,
        "email_smtp_username": "sales@example.com",
        "email_smtp_password": "secret",
        "email_smtp_last_test_at": "2026-04-04T10:00:00Z",
        "email_imap_host": "",
        "email_imap_port": 993,
        "email_imap_username": "",
        "email_imap_password": "",
        "email_use_tls": True,
        "email_daily_send_limit": 50,
        "email_hourly_send_limit": 10,
        "email_language_mode": "auto_by_region",
        "email_default_language": "en",
        "email_fallback_language": "en",
        "email_tone": "professional",
        "email_step1_delay_days": 0,
        "email_step2_delay_days": 3,
        "email_step3_delay_days": 3,
        "email_min_fit_score_to_send": 0.6,
        "email_min_contactability_score_to_send": 0.45,
    })())

    res = client.post("/api/v1/hunts/hunt_1/email-campaigns", json={"name": "Approved Only"})
    assert res.status_code == 200
    assert res.json()["sequence_count"] == 1


def test_create_campaign_includes_needs_review_when_approval_not_required(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)

    hunt = {
        "status": "completed",
        "result": {
            "email_sequences": [
                {
                    "lead": {"company_name": "Needs Review", "website": "https://review.com"},
                    "locale": "en_US",
                    "review_summary": {"status": "needs_review", "score": 61},
                    "auto_send_eligible": False,
                    "target": {
                        "target_email": "buyer@review.com",
                        "target_name": "Jane",
                        "target_title": "Purchasing Manager",
                        "target_type": "decision_maker_verified",
                    },
                    "emails": [
                        {"sequence_number": 1, "email_type": "company_intro", "subject": "Hi", "body_text": "A", "suggested_send_day": 0},
                    ],
                }
            ]
        },
    }

    monkeypatch.setattr("api.email_routes.load_hunt", lambda hunt_id: hunt)
    monkeypatch.setattr("api.email_routes.save_hunt", lambda hunt_id, data: None)
    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(tmp_path / "email.db"),
        "email_provider_type": "smtp",
        "email_from_name": "JPS One",
        "email_from_address": "sales@example.com",
        "email_reply_to": "sales@example.com",
        "email_smtp_host": "smtp.example.com",
        "email_smtp_port": 587,
        "email_smtp_username": "sales@example.com",
        "email_smtp_password": "secret",
        "email_smtp_last_test_at": "2026-04-04T10:00:00Z",
        "email_imap_host": "",
        "email_imap_port": 993,
        "email_imap_username": "",
        "email_imap_password": "",
        "email_use_tls": True,
        "email_daily_send_limit": 50,
        "email_hourly_send_limit": 10,
        "email_language_mode": "auto_by_region",
        "email_default_language": "en",
        "email_fallback_language": "en",
        "email_tone": "professional",
        "email_step1_delay_days": 0,
        "email_step2_delay_days": 3,
        "email_step3_delay_days": 3,
        "email_min_fit_score_to_send": 0.6,
        "email_min_contactability_score_to_send": 0.45,
        "email_require_approval_before_send": False,
    })())

    res = client.post("/api/v1/hunts/hunt_1/email-campaigns", json={"name": "Auto Approve Campaign"})
    assert res.status_code == 200
    assert res.json()["sequence_count"] == 1


def test_create_campaign_allows_previously_contacted_lead_email(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)

    hunt = {
        "status": "completed",
        "result": {
            "email_sequences": [
                {
                    "lead": {"company_name": "Acme", "website": "https://acme.com"},
                    "locale": "en_US",
                    "review_summary": {"status": "approved", "score": 92},
                    "auto_send_eligible": True,
                    "target": {
                        "target_email": "buyer@acme.com",
                        "target_name": "Jane",
                        "target_title": "Purchasing Manager",
                        "target_type": "decision_maker_verified",
                    },
                    "emails": [
                        {"sequence_number": 1, "email_type": "company_intro", "subject": "Hi", "body_text": "A", "suggested_send_day": 0},
                    ],
                }
            ]
        },
    }

    monkeypatch.setattr("api.email_routes.load_hunt", lambda hunt_id: hunt)
    monkeypatch.setattr("api.email_routes.save_hunt", lambda hunt_id, data: None)
    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(tmp_path / "email.db"),
        "email_provider_type": "smtp",
        "email_from_name": "JPS One",
        "email_from_address": "sales@example.com",
        "email_reply_to": "sales@example.com",
        "email_smtp_host": "smtp.example.com",
        "email_smtp_port": 587,
        "email_smtp_username": "sales@example.com",
        "email_smtp_password": "secret",
        "email_smtp_last_test_at": "2026-04-04T10:00:00Z",
        "email_imap_host": "",
        "email_imap_port": 993,
        "email_imap_username": "",
        "email_imap_password": "",
        "email_use_tls": True,
        "email_daily_send_limit": 50,
        "email_hourly_send_limit": 10,
        "email_language_mode": "auto_by_region",
        "email_default_language": "en",
        "email_fallback_language": "en",
        "email_tone": "professional",
        "email_step1_delay_days": 0,
        "email_step2_delay_days": 3,
        "email_step3_delay_days": 3,
        "email_min_fit_score_to_send": 0.6,
        "email_min_contactability_score_to_send": 0.45,
        "email_require_approval_before_send": True,
    })())

    first = client.post("/api/v1/hunts/hunt_1/email-campaigns", json={"name": "Campaign One"})
    second = client.post("/api/v1/hunts/hunt_1/email-campaigns", json={"name": "Campaign Two"})

    assert first.status_code == 200
    assert first.json()["sequence_count"] == 1
    assert second.status_code == 200
    assert second.json()["sequence_count"] == 1


def test_run_email_scheduler_route(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(tmp_path / "email.db"),
        "email_from_address": "sales@example.com",
        "email_smtp_host": "smtp.example.com",
        "email_smtp_port": 587,
        "email_smtp_username": "sales@example.com",
        "email_smtp_password": "secret",
        "email_smtp_last_test_at": "2026-04-04T10:00:00Z",
    })())

    called = {}

    async def fake_run_scheduler_once(store):
        called["db_path"] = store.db_path
        return {"sent": 1, "failed": 0, "skipped": 2}

    monkeypatch.setattr("api.email_routes.run_scheduler_once", fake_run_scheduler_once)

    res = client.post("/api/v1/email-scheduler/run")
    assert res.status_code == 200
    assert res.json() == {"sent": 1, "failed": 0, "skipped": 2}
    assert called["db_path"] == str(tmp_path / "email.db")


def test_run_email_reply_check_route(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(tmp_path / "email.db"),
        "email_provider_type": "smtp",
        "email_from_name": "JPS One",
        "email_from_address": "sales@example.com",
        "email_reply_to": "sales@example.com",
        "email_smtp_host": "smtp.example.com",
        "email_smtp_port": 587,
        "email_smtp_username": "sales@example.com",
        "email_smtp_password": "secret",
        "email_imap_host": "imap.example.com",
        "email_imap_port": 993,
        "email_imap_username": "sales@example.com",
        "email_imap_password": "imap-secret",
        "email_imap_last_test_at": "2026-04-04T10:00:00Z",
        "email_use_tls": True,
        "email_daily_send_limit": 50,
        "email_hourly_send_limit": 10,
    })())

    called = {}

    async def fake_run_reply_detection_once(store, account):
        called["db_path"] = store.db_path
        called["account_id"] = account["id"]
        return {"checked": 3, "matched": 1, "skipped": 2, "ignored": 1}

    monkeypatch.setattr("api.email_routes.run_reply_detection_once", fake_run_reply_detection_once)

    res = client.post("/api/v1/email-replies/check")
    assert res.status_code == 200
    assert res.json() == {"checked": 3, "matched": 1, "skipped": 2, "ignored": 1}
    assert called == {"db_path": str(tmp_path / "email.db"), "account_id": "default"}


def test_create_campaign_requires_smtp_configuration(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)

    hunt = {
        "status": "completed",
        "result": {
            "email_sequences": [
                {
                    "lead": {"company_name": "Acme", "website": "https://acme.com"},
                    "locale": "en_US",
                    "target": {
                        "target_email": "buyer@acme.com",
                        "target_name": "Jane",
                        "target_title": "Purchasing Manager",
                        "target_type": "decision_maker_verified",
                    },
                    "emails": [
                        {"sequence_number": 1, "email_type": "company_intro", "subject": "Hi", "body_text": "A", "suggested_send_day": 0},
                    ],
                }
            ]
        },
    }

    monkeypatch.setattr("api.email_routes.load_hunt", lambda hunt_id: hunt)
    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(tmp_path / "email.db"),
        "email_provider_type": "smtp",
        "email_from_name": "JPS One",
        "email_from_address": "",
        "email_reply_to": "",
        "email_smtp_host": "",
        "email_smtp_port": 0,
        "email_smtp_username": "",
        "email_smtp_password": "",
        "email_imap_host": "",
        "email_imap_port": 993,
        "email_imap_username": "",
        "email_imap_password": "",
        "email_use_tls": True,
        "email_daily_send_limit": 50,
        "email_hourly_send_limit": 10,
        "email_language_mode": "auto_by_region",
        "email_default_language": "en",
        "email_fallback_language": "en",
        "email_tone": "professional",
        "email_step1_delay_days": 0,
        "email_step2_delay_days": 3,
        "email_step3_delay_days": 3,
        "email_min_fit_score_to_send": 0.6,
        "email_min_contactability_score_to_send": 0.45,
    })())

    res = client.post("/api/v1/hunts/hunt_1/email-campaigns", json={"name": "Blocked Campaign"})
    assert res.status_code == 409
    assert "SMTP is not configured" in res.json()["detail"]


def test_start_campaign_requires_smtp_configuration(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(tmp_path / "email.db"),
        "email_from_address": "",
        "email_smtp_host": "",
        "email_smtp_port": 0,
        "email_smtp_username": "",
        "email_smtp_password": "",
    })())

    from emailing.store import EmailStore

    store = EmailStore(str(tmp_path / "email.db"))
    store.init_db()
    store.create_campaign({
        "id": "cmp_1",
        "hunt_id": "hunt_1",
        "email_account_id": "default",
        "name": "Test",
        "status": "draft",
        "language_mode": "auto_by_region",
        "default_language": "en",
        "fallback_language": "en",
        "tone": "professional",
        "step1_delay_days": 0,
        "step2_delay_days": 3,
        "step3_delay_days": 3,
        "min_fit_score": 0.6,
        "min_contactability_score": 0.45,
        "created_at": "2026-04-04T00:00:00Z",
        "updated_at": "2026-04-04T00:00:00Z",
    })

    res = client.post("/api/v1/email-campaigns/cmp_1/start")
    assert res.status_code == 409
    assert "SMTP is not configured" in res.json()["detail"]


def test_start_campaign_requires_smtp_test_success(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(tmp_path / "email.db"),
        "email_from_address": "sales@example.com",
        "email_smtp_host": "smtp.example.com",
        "email_smtp_port": 587,
        "email_smtp_username": "sales@example.com",
        "email_smtp_password": "secret",
        "email_smtp_last_test_at": "",
    })())

    from emailing.store import EmailStore

    store = EmailStore(str(tmp_path / "email.db"))
    store.init_db()
    store.create_campaign({
        "id": "cmp_2",
        "hunt_id": "hunt_1",
        "email_account_id": "default",
        "name": "Test",
        "status": "draft",
        "language_mode": "auto_by_region",
        "default_language": "en",
        "fallback_language": "en",
        "tone": "professional",
        "step1_delay_days": 0,
        "step2_delay_days": 3,
        "step3_delay_days": 3,
        "min_fit_score": 0.6,
        "min_contactability_score": 0.45,
        "created_at": "2026-04-04T00:00:00Z",
        "updated_at": "2026-04-04T00:00:00Z",
    })

    res = client.post("/api/v1/email-campaigns/cmp_2/start")
    assert res.status_code == 409
    assert "Please test SMTP in Settings" in res.json()["detail"]


def test_run_email_scheduler_requires_smtp_configuration(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(tmp_path / "email.db"),
        "email_from_address": "",
        "email_smtp_host": "",
        "email_smtp_port": 0,
        "email_smtp_username": "",
        "email_smtp_password": "",
    })())

    res = client.post("/api/v1/email-scheduler/run")
    assert res.status_code == 409
    assert "SMTP is not configured" in res.json()["detail"]


def test_run_email_scheduler_requires_smtp_test_success(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(tmp_path / "email.db"),
        "email_from_address": "sales@example.com",
        "email_smtp_host": "smtp.example.com",
        "email_smtp_port": 587,
        "email_smtp_username": "sales@example.com",
        "email_smtp_password": "secret",
        "email_smtp_last_test_at": "",
    })())

    res = client.post("/api/v1/email-scheduler/run")
    assert res.status_code == 409
    assert "Please test SMTP in Settings" in res.json()["detail"]


def test_run_email_reply_check_requires_imap_configuration(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(tmp_path / "email.db"),
        "email_imap_host": "",
        "email_imap_port": 0,
        "email_imap_username": "",
        "email_imap_password": "",
    })())

    res = client.post("/api/v1/email-replies/check")
    assert res.status_code == 409
    assert "IMAP is not configured" in res.json()["detail"]


def test_run_email_reply_check_requires_imap_test_success(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(tmp_path / "email.db"),
        "email_imap_host": "imap.example.com",
        "email_imap_port": 993,
        "email_imap_username": "sales@example.com",
        "email_imap_password": "secret",
        "email_imap_last_test_at": "",
    })())

    res = client.post("/api/v1/email-replies/check")
    assert res.status_code == 409
    assert "Please test IMAP in Settings" in res.json()["detail"]


def test_email_routes_require_token_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("API_ACCESS_TOKEN", "secret-token")
    from config.settings import get_settings

    get_settings.cache_clear()
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(tmp_path / "email.db"),
        "email_provider_type": "smtp",
        "email_from_name": "JPS One",
        "email_from_address": "sales@example.com",
        "email_reply_to": "sales@example.com",
        "email_smtp_host": "smtp.example.com",
        "email_smtp_port": 587,
        "email_smtp_username": "sales@example.com",
        "email_smtp_password": "secret",
        "email_smtp_last_test_at": "2026-04-04T10:00:00Z",
        "email_imap_host": "",
        "email_imap_port": 993,
        "email_imap_username": "",
        "email_imap_password": "",
        "email_use_tls": True,
        "email_daily_send_limit": 50,
        "email_hourly_send_limit": 10,
        "api_access_token": "secret-token",
    })())

    unauthorized = client.post("/api/v1/email-scheduler/run")
    authorized = client.post("/api/v1/email-scheduler/run", headers={"X-API-Key": "secret-token"})

    get_settings.cache_clear()
    assert unauthorized.status_code == 401
    assert authorized.status_code == 200


def test_one_click_preview_overrides_flow_into_start(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)
    db_path = tmp_path / "email.db"

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(db_path),
        "email_provider_type": "smtp",
        "email_from_name": "JPS One",
        "email_from_address": "sales@example.com",
        "email_reply_to": "sales@example.com",
        "email_smtp_host": "smtp.example.com",
        "email_smtp_port": 587,
        "email_smtp_username": "sales@example.com",
        "email_smtp_password": "secret",
        "email_smtp_last_test_at": "2026-04-04T10:00:00Z",
        "email_imap_host": "",
        "email_imap_port": 993,
        "email_imap_username": "",
        "email_imap_password": "",
        "email_use_tls": True,
        "email_daily_send_limit": 50,
        "email_hourly_send_limit": 10,
        "email_language_mode": "auto_by_region",
        "email_default_language": "en",
        "email_fallback_language": "en",
        "email_tone": "professional",
        "email_min_fit_score_to_send": 0.6,
        "email_min_contactability_score_to_send": 0.45,
    })())

    store = EmailStore(str(db_path))
    store.init_db()
    store.upsert_contact_profile({
        "id": "profile_1",
        "hunt_id": "hunt_one_click",
        "candidate_id": "candidate_1",
        "lead_id": "lead_1",
        "company_name": "Bangkok Dental Academy",
        "recipient_email": "info@bda.example",
        "recipient_name": "Admissions Team",
        "website": "https://bda.example",
        "country_or_region": "Thailand",
        "customer_type": "dental training center",
        "company_summary": "Dental simulator training center.",
        "jps_fit_reason": "Uses phantom head training rooms.",
        "matched_product_keywords_json": json.dumps(["dental simulator"]),
        "evidence_urls_json": json.dumps(["https://bda.example/about"]),
        "send_eligibility": "sendable",
        "variables_json": json.dumps({
            "company_name": "Bangkok Dental Academy",
            "recipient_name": "Admissions Team",
            "recipient_email": "info@bda.example",
        }),
        "created_at": "2026-07-29T00:00:00Z",
        "updated_at": "2026-07-29T00:00:00Z",
    })

    payload = {
        "subject_template": "Template for {{company_name}}",
        "body_template": "Hi {{recipient_name}}, template body",
        "overrides": {
            "profile_1": {
                "subject": "Custom subject",
                "body_text": "Custom body for this customer",
            }
        },
    }
    preview = client.post("/api/v1/email/tasks/hunt_one_click/one-click/preview", json=payload)
    assert preview.status_code == 200
    assert preview.json()["previews"][0]["edited"] is True
    assert preview.json()["previews"][0]["subject"] == "Custom subject"
    assert preview.json()["previews"][0]["company_summary"] == "Dental simulator training center."

    started = client.post("/api/v1/email/tasks/hunt_one_click/one-click/start", json=payload)
    assert started.status_code == 200
    campaign_id = started.json()["campaign_id"]
    sequence = store.list_sequences_for_campaign(campaign_id)[0]
    message = store.get_message_for_step(sequence["id"], 1)
    assert message["subject"] == "Custom subject"
    assert message["body_text"] == "Custom body for this customer"


def test_one_click_start_blocks_when_send_limit_exceeded(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)
    db_path = tmp_path / "email.db"

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {
        "email_db_path": str(db_path),
        "email_provider_type": "smtp",
        "email_from_name": "JPS One",
        "email_from_address": "sales@example.com",
        "email_reply_to": "sales@example.com",
        "email_smtp_host": "smtp.example.com",
        "email_smtp_port": 587,
        "email_smtp_username": "sales@example.com",
        "email_smtp_password": "secret",
        "email_smtp_last_test_at": "2026-04-04T10:00:00Z",
        "email_imap_host": "",
        "email_imap_port": 993,
        "email_imap_username": "",
        "email_imap_password": "",
        "email_use_tls": True,
        "email_timezone": "UTC",
        "email_daily_send_limit": 100,
        "email_hourly_send_limit": 1,
        "email_language_mode": "auto_by_region",
        "email_default_language": "en",
        "email_fallback_language": "en",
        "email_tone": "professional",
        "email_min_fit_score_to_send": 0.6,
        "email_min_contactability_score_to_send": 0.45,
    })())

    store = EmailStore(str(db_path))
    store.init_db()
    store.upsert_contact_profile({
        "id": "profile_limit",
        "hunt_id": "hunt_limit",
        "candidate_id": "candidate_limit",
        "company_name": "Limit Dental",
        "recipient_email": "info@limit.example",
        "matched_product_keywords_json": "[]",
        "evidence_urls_json": "[]",
        "send_eligibility": "sendable",
        "variables_json": json.dumps({"company_name": "Limit Dental", "recipient_email": "info@limit.example"}),
        "created_at": "2026-07-30T00:00:00Z",
        "updated_at": "2026-07-30T00:00:00Z",
    })
    store.create_campaign({
        "id": "cmp_limit",
        "hunt_id": "hunt_other",
        "email_account_id": "default",
        "name": "Already sent",
        "status": "active",
        "language_mode": "auto_by_region",
        "default_language": "en",
        "fallback_language": "en",
        "tone": "professional",
        "step1_delay_days": 0,
        "step2_delay_days": 3,
        "step3_delay_days": 3,
        "min_fit_score": 0.6,
        "min_contactability_score": 0.45,
        "created_at": "2026-07-30T00:00:00Z",
        "updated_at": "2026-07-30T00:00:00Z",
    })
    store.create_sequence({
        "id": "seq_limit",
        "campaign_id": "cmp_limit",
        "hunt_id": "hunt_other",
        "lead_key": "other|sent@example.com",
        "lead_email": "sent@example.com",
        "lead_name": "Sent",
        "locale": "en",
        "status": "completed",
        "current_step": 1,
        "created_at": "2026-07-30T00:00:00Z",
        "updated_at": "2026-07-30T00:00:00Z",
    })
    store.create_message({
        "id": "msg_limit",
        "sequence_id": "seq_limit",
        "step_number": 1,
        "goal": "one_click_outreach",
        "locale": "en",
        "subject": "Sent",
        "body_text": "Sent",
        "status": "smtp_accepted",
        "scheduled_at": "2026-07-30T00:00:00Z",
        "sent_at": "2026-07-30T00:30:00+00:00",
        "provider_message_id": "",
        "thread_key": "",
        "failure_reason": "",
        "created_at": "2026-07-30T00:00:00Z",
        "updated_at": "2026-07-30T00:30:00+00:00",
    })

    monkeypatch.setattr("api.email_routes.now_iso", lambda: "2026-07-30T01:00:00+00:00")
    res = client.post("/api/v1/email/tasks/hunt_limit/one-click/start", json={
        "subject_template": "Hello {{company_name}}",
        "body_template": "Hi {{company_name}}",
    })

    assert res.status_code == 409
    assert "本小时剩余可发送 0 封" in res.json()["detail"]


def test_one_click_preview_maps_operator_template_variables(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)
    db_path = tmp_path / "email.db"

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {"email_db_path": str(db_path)})())
    store = EmailStore(str(db_path))
    store.init_db()
    store.upsert_contact_profile({
        "id": "profile_safe",
        "hunt_id": "hunt_safe",
        "candidate_id": "candidate_safe",
        "company_name": "Thailand Dental Training Center",
        "recipient_email": "info@safe.example",
        "website": "https://safe.example",
        "company_summary": "A public dental training center in Bangkok.",
        "jps_fit_reason": "目标类型 media_not_customer；来源 tavily_mcp；业务规则扣分 105",
        "matched_product_keywords_json": "[]",
        "evidence_urls_json": "[]",
        "send_eligibility": "sendable",
        "variables_json": json.dumps({
            "company_name": "Thailand Dental Training Center",
            "recipient_name": "there",
            "recipient_email": "info@safe.example",
            "company_summary": "A public dental training center in Bangkok.",
            "jps_fit_reason": "目标类型 media_not_customer；来源 tavily_mcp；业务规则扣分 105",
        }),
        "created_at": "2026-07-29T00:00:00Z",
        "updated_at": "2026-07-29T00:00:00Z",
    })

    res = client.post("/api/v1/email/tasks/hunt_safe/one-click/preview", json={
        "subject_template": "JPS dental training products for {{company_name}}",
        "body_template": "Hi {{recipient_name}}, JPS supplies {{product_pitch}}. Internal {{jps_fit_reason}}",
    })

    assert res.status_code == 200
    item = res.json()["previews"][0]
    assert item["send_eligibility"] == "sendable"
    assert item["render_status"] == "invalid_variables"
    assert item["invalid_variables"] == ["jps_fit_reason"]
    assert "{{jps_fit_reason}}" in item["body_text"]
    assert "media_not_customer" not in item["body_text"]


def test_template_chat_only_extracts_template_variables(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)
    db_path = tmp_path / "email.db"

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {"email_db_path": str(db_path)})())
    store = EmailStore(str(db_path))
    store.init_db()
    store.upsert_contact_profile({
        "id": "profile_template",
        "hunt_id": "hunt_template",
        "candidate_id": "candidate_template",
        "company_name": "Template Dental",
        "recipient_email": "info@template.example",
        "matched_product_keywords_json": json.dumps(["dental simulator"]),
        "evidence_urls_json": "[]",
        "send_eligibility": "sendable",
        "variables_json": "{}",
        "created_at": "2026-07-29T00:00:00Z",
        "updated_at": "2026-07-29T00:00:00Z",
    })

    res = client.post("/api/v1/email/tasks/hunt_template/template/chat", json={
        "message": "Subject: Hello {{company_name}}\nBody: Hi {{recipient_name}}, we provide {{product_pitch}}."
    })

    assert res.status_code == 200
    data = res.json()
    assert data["subject_template"] == "Hello {{company_name}}"
    assert data["body_template"] == "Hi {{recipient_name}}, we provide {{product_pitch}}."
    assert data["used_variables"] == ["company_name", "recipient_name", "product_pitch"]
    assert data["invalid_variables"] == []


def test_contact_profile_update_syncs_back_to_hunt(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)
    db_path = tmp_path / "email.db"
    hunt = {
        "status": "completed",
        "result": {
            "candidate_pool": [{"candidate_id": "candidate_sync", "company_name": "Sync Dental", "website": "https://sync.example", "emails": []}],
            "leads": [{"candidate_id": "candidate_sync", "company_name": "Sync Dental", "website": "https://sync.example", "emails": []}],
        },
    }
    saved = {}

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {"email_db_path": str(db_path)})())
    monkeypatch.setattr("emailing.contact_sync.load_hunt", lambda hunt_id: hunt)
    monkeypatch.setattr("emailing.contact_sync.save_hunt", lambda hunt_id, data: saved.update({hunt_id: data}))

    store = EmailStore(str(db_path))
    store.init_db()
    store.upsert_contact_profile({
        "id": "profile_sync",
        "hunt_id": "hunt_sync",
        "candidate_id": "candidate_sync",
        "company_name": "Sync Dental",
        "recipient_email": "",
        "website": "https://sync.example",
        "matched_product_keywords_json": "[]",
        "evidence_urls_json": "[]",
        "send_eligibility": "missing_email",
        "variables_json": "{}",
        "lead_snapshot_json": json.dumps({"candidate_id": "candidate_sync", "website": "https://sync.example"}),
        "created_at": "2026-07-29T00:00:00Z",
        "updated_at": "2026-07-29T00:00:00Z",
    })

    res = client.post("/api/v1/email/contact-profiles/profile_sync/update", json={"recipient_email": "Sales@Sync.Example"})

    assert res.status_code == 200
    assert res.json()["profile"]["sync_result"]["synced"] is True
    updated = saved["hunt_sync"]["result"]
    assert updated["candidate_pool"][0]["emails"] == ["sales@sync.example"]
    assert updated["leads"][0]["email"] == "sales@sync.example"
    assert updated["leads"][0]["evidence_items"][0]["source"] == "manual_email_update"


def test_exclude_and_restore_contact_profile_send_list(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)
    db_path = tmp_path / "email.db"

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {"email_db_path": str(db_path)})())
    store = EmailStore(str(db_path))
    store.init_db()
    store.upsert_contact_profile({
        "id": "profile_send_list",
        "hunt_id": "hunt_send_list",
        "candidate_id": "candidate_send_list",
        "company_name": "Send List Dental",
        "recipient_email": "info@sendlist.example",
        "matched_product_keywords_json": "[]",
        "evidence_urls_json": "[]",
        "send_eligibility": "sendable",
        "variables_json": json.dumps({"company_name": "Send List Dental", "recipient_email": "info@sendlist.example"}),
        "created_at": "2026-07-30T00:00:00Z",
        "updated_at": "2026-07-30T00:00:00Z",
    })

    excluded = client.post("/api/v1/email/contact-profiles/profile_send_list/exclude-from-send")
    assert excluded.status_code == 200
    assert excluded.json()["profile"]["send_eligibility"] == "manually_excluded"

    preview = client.post("/api/v1/email/tasks/hunt_send_list/one-click/preview", json={
        "subject_template": "Hello {{company_name}}",
        "body_template": "Hi {{company_name}}",
    })
    assert preview.status_code == 200
    assert preview.json()["sendable_count"] == 0
    assert preview.json()["skipped"][0]["send_eligibility"] == "manually_excluded"

    task = client.get("/api/v1/email/tasks/hunt_send_list")
    assert task.status_code == 200
    assert task.json()["profiles"][0]["company_name"] == "Send List Dental"

    restored = client.post("/api/v1/email/contact-profiles/profile_send_list/restore-to-send")
    assert restored.status_code == 200
    assert restored.json()["profile"]["send_eligibility"] == "sendable"


def test_restore_without_email_returns_missing_email(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)
    db_path = tmp_path / "email.db"

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {"email_db_path": str(db_path)})())
    store = EmailStore(str(db_path))
    store.init_db()
    store.upsert_contact_profile({
        "id": "profile_no_email",
        "hunt_id": "hunt_no_email",
        "candidate_id": "candidate_no_email",
        "company_name": "No Email Dental",
        "recipient_email": "",
        "matched_product_keywords_json": "[]",
        "evidence_urls_json": "[]",
        "send_eligibility": "manually_excluded",
        "skip_reason": "业务员已从本次邮件发送名单移除",
        "variables_json": "{}",
        "created_at": "2026-07-30T00:00:00Z",
        "updated_at": "2026-07-30T00:00:00Z",
    })

    restored = client.post("/api/v1/email/contact-profiles/profile_no_email/restore-to-send")
    assert restored.status_code == 200
    assert restored.json()["profile"]["send_eligibility"] == "missing_email"
    assert restored.json()["profile"]["skip_reason"] == "缺少可发送邮箱"


def test_email_template_library_create_apply_and_delete(monkeypatch, tmp_path):
    app = create_app()
    client = TestClient(app)
    db_path = tmp_path / "email.db"

    monkeypatch.setattr("api.email_routes.get_settings", lambda: type("S", (), {"email_db_path": str(db_path)})())
    store = EmailStore(str(db_path))
    store.init_db()
    store.upsert_contact_profile({
        "id": "profile_template",
        "hunt_id": "hunt_template",
        "candidate_id": "candidate_template",
        "company_name": "Template Dental School",
        "recipient_email": "info@template.example",
        "recipient_name": "Dr. Lee",
        "website": "https://template.example",
        "country_or_region": "Thailand",
        "customer_type": "dental school",
        "matched_product_keywords_json": json.dumps(["dental simulator"]),
        "evidence_urls_json": "[]",
        "send_eligibility": "sendable",
        "variables_json": "{}",
        "created_at": "2026-07-30T00:00:00Z",
        "updated_at": "2026-07-30T00:00:00Z",
    })

    created = client.post("/api/v1/email/templates", json={
        "name": "Dental school intro",
        "category": "development",
        "language": "en",
        "product_tags": ["dental simulator"],
        "customer_type_tags": ["dental school"],
        "subject_template": "JPS training products for {{company_name}}",
        "body_template": "Hi {{recipient_name}}, we support {{customer_type}} with {{product_pitch}}.",
    })
    assert created.status_code == 200
    template = created.json()
    assert template["name"] == "Dental school intro"
    assert template["used_variables"] == ["company_name", "recipient_name", "customer_type", "product_pitch"]

    listed = client.get("/api/v1/email/templates")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [template["id"]]

    applied = client.post("/api/v1/email/tasks/hunt_template/template/apply", json={"template_id": template["id"]})
    assert applied.status_code == 200
    assert applied.json()["subject_template"] == template["subject_template"]
    assert applied.json()["template"]["usage_count"] == 1

    preview = client.post("/api/v1/email/tasks/hunt_template/one-click/preview", json={})
    assert preview.status_code == 200
    assert preview.json()["sendable_count"] == 1
    assert "Template Dental School" in preview.json()["previews"][0]["subject"]
    assert "Dr. Lee" in preview.json()["previews"][0]["body_text"]

    deleted = client.delete(f"/api/v1/email/templates/{template['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["id"] == template["id"]
    assert client.get("/api/v1/email/templates").json() == []
