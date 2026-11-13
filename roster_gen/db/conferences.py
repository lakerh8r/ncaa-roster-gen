"""2026 conference assignments for NCAA 14 base-roster teams (Phase A).

Maps team name -> CGID (conference ID from the base CONF table).
Conference IDs: 0=ACC, 1=Big Ten, 2=Big 12, 3=American, 4=C-USA,
5=Independents, 7=MAC, 9=MWC, 10=Pac-12, 11=SEC, 13=Sun Belt.
"""

CONF_NAME_TO_ID = {
    "SEC": 11,
    "Big Ten": 1,
    "Big 12": 2,
    "ACC": 0,
    "American": 3,
    "Mountain West": 9,
    "Sun Belt": 13,
    "MAC": 7,
    "C-USA": 4,
    "Pac-12": 10,
    "Independents": 5,
}

SEC = ["Alabama", "Arkansas", "Auburn", "Florida", "Georgia", "Kentucky",
       "LSU", "Mississippi State", "Missouri", "Ole Miss", "South Carolina",
       "Tennessee", "Texas A&M", "Texas", "Oklahoma", "Vanderbilt"]
BIG_TEN = ["Illinois", "Indiana", "Iowa", "Maryland", "Michigan", "Michigan State",
            "Minnesota", "Nebraska", "Northwestern", "Ohio State", "Penn State",
            "Purdue", "Rutgers", "Wisconsin", "USC", "UCLA", "Oregon", "Washington"]
BIG_12 = ["Arizona", "Arizona State", "Baylor", "BYU", "Cincinnati", "Colorado",
          "Houston", "Iowa State", "Kansas", "Kansas State", "Oklahoma State",
          "TCU", "Texas Tech", "UCF", "Utah", "West Virginia"]
ACC = ["Boston College", "Clemson", "Duke", "Florida State", "Georgia Tech",
       "Louisville", "Miami", "NC State", "North Carolina", "Pittsburgh",
       "Syracuse", "Virginia", "Virginia Tech", "Wake Forest", "California",
       "Stanford", "SMU"]
AMERICAN = ["Army", "Charlotte", "ECU", "Florida Atlantic", "Memphis", "Navy",
            "North Texas", "Rice", "South Florida", "Temple", "Tulane", "Tulsa",
            "UAB", "UTSA"]
MWC = ["Air Force", "Hawaii", "Nevada", "New Mexico", "San Jose State", "UNLV",
       "Wyoming", "UTEP", "Northern Illinois"]
SUN_BELT = ["Appalachian State", "Arkansas State", "Coastal Carolina",
             "Georgia Southern", "Georgia State", "James Madison", "Louisiana",
             "Louisiana Tech", "Marshall", "Old Dominion", "South Alabama",
             "Southern Miss", "Troy", "UL Monroe", "UL Lafayette"]
MAC = ["Akron", "Ball State", "Bowling Green", "Buffalo", "Central Michigan",
       "Eastern Michigan", "Kent State", "Miami (OH)", "Miami University",
       "Ohio", "Toledo", "Western Michigan", "UMass"]
CUSA = ["FIU", "Jacksonville State", "Kennesaw State", "Liberty",
        "Middle Tennessee", "Mid Tenn State", "New Mexico State", "Sam Houston",
        "Western Kentucky"]
PAC_12 = ["Oregon State", "Washington State", "Boise State", "Colorado State",
          "Fresno State", "San Diego State", "Texas State", "Utah State"]
INDEPENDENTS = ["Notre Dame", "UConn"]

TEAM_CONFERENCE = {}
for t in SEC:
    TEAM_CONFERENCE[t] = CONF_NAME_TO_ID["SEC"]
for t in BIG_TEN:
    TEAM_CONFERENCE[t] = CONF_NAME_TO_ID["Big Ten"]
for t in BIG_12:
    TEAM_CONFERENCE[t] = CONF_NAME_TO_ID["Big 12"]
for t in ACC:
    TEAM_CONFERENCE[t] = CONF_NAME_TO_ID["ACC"]
for t in AMERICAN:
    TEAM_CONFERENCE[t] = CONF_NAME_TO_ID["American"]
for t in MWC:
    TEAM_CONFERENCE[t] = CONF_NAME_TO_ID["Mountain West"]
for t in SUN_BELT:
    TEAM_CONFERENCE[t] = CONF_NAME_TO_ID["Sun Belt"]
for t in MAC:
    TEAM_CONFERENCE[t] = CONF_NAME_TO_ID["MAC"]
for t in CUSA:
    TEAM_CONFERENCE[t] = CONF_NAME_TO_ID["C-USA"]
for t in PAC_12:
    TEAM_CONFERENCE[t] = CONF_NAME_TO_ID["Pac-12"]
for t in INDEPENDENTS:
    TEAM_CONFERENCE[t] = CONF_NAME_TO_ID["Independents"]

# Aliases
TEAM_CONFERENCE["Miami University"] = CONF_NAME_TO_ID["MAC"]
TEAM_CONFERENCE["Mid Tenn State"] = CONF_NAME_TO_ID["C-USA"]
TEAM_CONFERENCE["ECU"] = CONF_NAME_TO_ID["American"]
TEAM_CONFERENCE["UL Lafayette"] = CONF_NAME_TO_ID["Sun Belt"]
TEAM_CONFERENCE["USF"] = CONF_NAME_TO_ID["American"]
TEAM_CONFERENCE["FIU"] = CONF_NAME_TO_ID["C-USA"]
TEAM_CONFERENCE["San Jose State"] = CONF_NAME_TO_ID["Mountain West"]


def get_conference_id(team_name):
    return TEAM_CONFERENCE.get(team_name)


# Prestige tiers (Power 4 / Group of 6 / Independents)
PRESTIGE_TIER = {}
for t in SEC + BIG_TEN + BIG_12 + ACC:
    PRESTIGE_TIER[t] = "power4"
for t in AMERICAN + MWC + SUN_BELT + MAC + CUSA + PAC_12:
    PRESTIGE_TIER[t] = "g6"
for t in INDEPENDENTS:
    PRESTIGE_TIER[t] = "independent"

# Aliases for prestige
PRESTIGE_TIER["Miami University"] = "g6"
PRESTIGE_TIER["Mid Tenn State"] = "g6"
PRESTIGE_TIER["ECU"] = "g6"
PRESTIGE_TIER["UL Lafayette"] = "g6"
PRESTIGE_TIER["USF"] = "g6"
PRESTIGE_TIER["FIU"] = "g6"
PRESTIGE_TIER["San Jose State"] = "g6"


def prestige_for(team_name, avg_ovr):
    """Compute prestige (0-6 scale) based on tier and team OVR."""
    tier = PRESTIGE_TIER.get(team_name, "g6")
    if tier == "power4":
        base = 4
    elif tier == "independent":
        base = 4
    else:
        base = 1
    # scale within tier by OVR
    bonus = int((avg_ovr - 70) / 15)
    return max(0, min(6, base + bonus))