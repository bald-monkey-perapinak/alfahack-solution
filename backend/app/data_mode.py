def company_filter(mode):
    clause = "profile_data <> '{}'"
    if mode == "organizers":
        clause += " AND left(synthetic_u,2)='U_'"
    return clause


def material_filter(mode, kind="news"):
    clause = "processing_status='ready'"
    if kind == "bank_analytics":
        clause += " AND material_type='bank_analytics'"
    elif mode == "organizers":
        clause += " AND (material_type='news' OR (material_type='bank_analytics' AND analysis_data->>'analysis_eligible'='true'))"
    else:
        clause += " AND material_type='news'"
    if mode == "organizers":
        clause += " AND NOT is_demo"
    return clause
