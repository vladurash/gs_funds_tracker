DOMAIN = "gs_funds_tracker"
DEFAULT_RESOURCE_URL = "https://am.gs.com/services/funds"
DEFAULT_SCAN_INTERVAL = 3600

GRAPHQL_QUERY = (
    "query getFundsDetail($fundDetailRequest: FundDetailRequest) { "
    "fundsDetail(fundDetailRequest: $fundDetailRequest) { "
    "id: shareClassId fundName isin scBaseCurrency quickStats { "
    "label asAtDate value currency upDownValue upDownPctValue } } }"
)
