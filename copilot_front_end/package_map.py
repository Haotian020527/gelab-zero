import difflib

package_name_map = {
    "YouTube": "com.forvia.youtube",
    "Teams": "com.forvia.meetingsforteams.aaos",
    "日历": "com.android.calendar",
    "Spotify": "com.fce.onlinemedia",
    "地图": "com.generalmagic.magicearth",
    "APPStore": "com.forvia.demo.appstore"
}

import difflib 

def find_package_name(app_name):
    app_name_lowered = app_name.lower()
    package_name = package_name_map.get(app_name_lowered, None)
    
    max_match = {
        "name": None,
        "score": 0
    }
    
    if package_name is None:
        # to search a similar app name
        for key in package_name_map.keys():
            # Use the lowercase input for comparison
            score = difflib.SequenceMatcher(None, app_name_lowered, key.lower()).ratio() 
            
            if score > max_match["score"]:
                max_match["name"] = key
                max_match["score"] = score
        
        # Check if a match was found with a score > 0 (or some threshold, though the assert below only checks if name is not None)
        assert max_match['name'] is not None, f"Cannot find package name for app {app_name}"
        
        # We retrieve the actual package name using the original (correctly cased) key from the map
        package_name = package_name_map[max_match['name']]

    return package_name


def get_list_of_package_names():
    """
    Return a list of all package names.
    """
    applications = [{"app_name": app_name, "package_name": package_name} for app_name, package_name in package_name_map.items()]
    return applications
