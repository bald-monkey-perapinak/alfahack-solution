import csv

from backend.manage import import_companies, import_links, import_payments


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def test_import_conflicts_stubs_and_payment_snapshot(system, tmp_path):
    _, db, _ = system
    companies = tmp_path / "df_Uid_data_hack.csv"
    write_csv(
        companies,
        ["SYNTHETIC_U", "REVENUE_COMPANY", "MAINOKVED_CODE"],
        [
            {"SYNTHETIC_U": "IMPORT_A", "REVENUE_COMPANY": "1000", "MAINOKVED_CODE": "01.11"},
            {"SYNTHETIC_U": "CONFLICT", "REVENUE_COMPANY": "1000", "MAINOKVED_CODE": "01.11"},
            {"SYNTHETIC_U": "CONFLICT", "REVENUE_COMPANY": "2000", "MAINOKVED_CODE": "01.11"},
        ],
    )
    report = import_companies(db, companies)
    assert report["conflicting_profile_count"] == 1
    assert db.one("SELECT profile_data FROM organizations WHERE synthetic_u='CONFLICT'")["profile_data"] == {}
    assert (
        db.one("SELECT okved_code FROM organizations WHERE synthetic_u='IMPORT_A'")["okved_code"] == "01.11"
    )
    write_csv(
        tmp_path / "df_Fid_Uid_link_hack.csv",
        ["SYNTHETIC_F", "SYNTHETIC_U", "CITY_NAME", "RC_NAME"],
        [{"SYNTHETIC_F": "IMPORT_F", "SYNTHETIC_U": "UNKNOWN_B", "CITY_NAME": "", "RC_NAME": ""}],
    )
    import_links(db, tmp_path)
    write_csv(
        tmp_path / "df_Uid_payment_hack.csv",
        ["PAYER", "BENEFICIARY", "PAY_AMT", "PAY_CNT"],
        [
            {"PAYER": "IMPORT_A", "BENEFICIARY": "UNKNOWN_B", "PAY_AMT": "1000", "PAY_CNT": "1"},
            {"PAYER": "IMPORT_A", "BENEFICIARY": "UNKNOWN_B", "PAY_AMT": "2000", "PAY_CNT": "2"},
            {"PAYER": "IMPORT_A", "BENEFICIARY": "IMPORT_A", "PAY_AMT": "100", "PAY_CNT": "1"},
        ],
    )
    import_payments(db, tmp_path)
    import_payments(db, tmp_path)
    assert db.one("SELECT count(*) AS n FROM payment_flows")["n"] == 3
    assert (
        db.one("SELECT profile_data FROM organizations WHERE synthetic_u='UNKNOWN_B'")["profile_data"] == {}
    )
