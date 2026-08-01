from candidate_pool import build_candidate_pool


def test_goal_guard_prioritizes_dental_school_over_supplier_for_school_task():
    rows = [
        {
            "title": "Dentech Corporation",
            "link": "https://dentech.example",
            "source": "tavily",
            "snippet": "Dental equipment supplier and manufacturer with phone, email and showroom.",
            "evidence": {"email": "sales@dentech.example", "phone": "+66 2123 4567"},
        },
        {
            "title": "Faculty of Dentistry Mahidol University",
            "link": "https://dt.mahidol.ac.th",
            "source": "tavily",
            "snippet": "Faculty of Dentistry university preclinical simulation lab and dental teaching program in Thailand.",
        },
    ]

    candidates = build_candidate_pool(
        rows,
        target_final_leads=1,
        customer_types=["dental school", "dental training center"],
        product_keywords=["dental simulator", "phantom head"],
        target_regions=["Thailand"],
        exclusions=["ordinary dental clinic"],
    )

    assert candidates[0]["company_name"] == "Faculty of Dentistry Mahidol University"
    assert candidates[0]["target_type"] == "dental_school"
    assert candidates[0]["target_type_fit_score"] >= 90
    assert candidates[1]["target_type_fit_score"] < candidates[0]["target_type_fit_score"]


def test_goal_guard_demotes_manufacturer_for_distributor_task():
    rows = [
        {
            "title": "Thai Dental Dealer Co Ltd",
            "link": "https://dealer.example",
            "source": "google_maps",
            "snippet": "Authorized dental equipment distributor and importer in Bangkok.",
        },
        {
            "title": "Nissin Dental Products",
            "link": "https://nissin.example",
            "source": "tavily",
            "snippet": "Dental simulator manufacturer and factory producing phantom head training products.",
        },
    ]

    candidates = build_candidate_pool(
        rows,
        target_final_leads=1,
        customer_types=["dental equipment distributor", "agent"],
        product_keywords=["dental simulator"],
        target_regions=["Thailand"],
    )

    assert candidates[0]["company_name"] == "Thai Dental Dealer Co Ltd"
    manufacturer = next(item for item in candidates if item["company_name"] == "Nissin Dental Products")
    assert manufacturer["candidate_status"] == "excluded_by_goal"
    assert "manufacturer_when_distributor_requested" in manufacturer["goal_drift_flags"]


def test_goal_guard_keeps_complete_contacts_as_bonus_not_primary_rank():
    rows = [
        {
            "title": "Bangkok Smile Dental Clinic",
            "link": "https://clinic.example",
            "source": "google_maps",
            "snippet": "Dental clinic with Instagram, email, phone and address.",
            "evidence": {"email": "info@clinic.example", "phone": "+66 2999 9999"},
            "social_media": {"instagram": "https://instagram.com/bangkoksmile"},
        },
        {
            "title": "Chulalongkorn University Faculty of Dentistry",
            "link": "https://dent.chula.ac.th",
            "source": "tavily",
            "snippet": "University Faculty of Dentistry teaching lab for dental simulator and phantom head training.",
        },
    ]

    candidates = build_candidate_pool(
        rows,
        target_final_leads=1,
        hard_filters={"require_instagram": True, "require_email": True, "require_phone": True},
        customer_types=["dental school", "training center"],
        product_keywords=["dental simulator"],
        exclusions=["ordinary dental clinic", "dental clinic"],
    )

    assert candidates[0]["company_name"] == "Chulalongkorn University Faculty of Dentistry"
    clinic = next(item for item in candidates if item["company_name"] == "Bangkok Smile Dental Clinic")
    assert clinic["candidate_status"] == "excluded_by_goal"


def test_goal_guard_demotes_confirmed_out_of_region_candidate_for_thailand_task():
    rows = [
        {
            "title": "DSTC Dental Specialty Training Center",
            "link": "https://dstc.ca",
            "source": "tavily",
            "snippet": "Dental specialty training center in Toronto, Canada with contact information.",
            "country": "Canada",
            "evidence": {"email": "info@dstc.ca", "phone": "+1 416 000 0000"},
        },
        {
            "title": "Mahidol University Faculty of Dentistry",
            "link": "https://dt.mahidol.ac.th",
            "source": "tavily",
            "snippet": "Faculty of Dentistry in Bangkok, Thailand with dental simulation laboratory.",
        },
    ]

    candidates = build_candidate_pool(
        rows,
        target_final_leads=1,
        customer_types=["dental school", "training center"],
        product_keywords=["dental simulator"],
        target_regions=["Thailand"],
    )

    assert candidates[0]["company_name"] == "Mahidol University Faculty of Dentistry"
    canada = next(item for item in candidates if item["company_name"] == "DSTC Dental Specialty Training Center")
    assert canada["region_fit_score"] == 0
    assert canada["candidate_status"] == "excluded_by_goal"
    assert "region_mismatch_confirmed" in canada["goal_drift_flags"]


def test_goal_guard_keeps_unknown_region_below_confirmed_target_region():
    rows = [
        {
            "title": "Unknown Dental Training Center",
            "link": "https://training.example",
            "source": "tavily",
            "snippet": "Dental training center with phantom head simulation courses.",
        },
        {
            "title": "Chulalongkorn University Faculty of Dentistry",
            "link": "https://dent.chula.ac.th",
            "source": "tavily",
            "snippet": "Faculty of Dentistry university in Bangkok, Thailand with preclinical training lab.",
        },
    ]

    candidates = build_candidate_pool(
        rows,
        target_final_leads=1,
        customer_types=["dental school", "training center"],
        product_keywords=["dental simulator"],
        target_regions=["Thailand"],
    )

    assert candidates[0]["company_name"] == "Chulalongkorn University Faculty of Dentistry"
    unknown = next(item for item in candidates if item["company_name"] == "Unknown Dental Training Center")
    assert unknown["region_fit_score"] == 55
    assert "region_unknown" in unknown["goal_drift_flags"]
