import math


def area_from_record(row: dict) -> dict | None:
    try:
        latitude, longitude = float(row["latitude"]), float(row["longitude"])
        if not (-85 <= latitude <= 85 and -180 <= longitude <= 180):
            return None
        latitudes = [row.get("minLatitude"), row.get("maxLatitude")]
        longitudes = [row.get("minLongitude"), row.get("maxLongitude")]
        if all(value is not None for value in latitudes + longitudes):
            south, north = sorted(map(float, latitudes))
            west, east = sorted(map(float, longitudes))
            kind = "gazetteer bounding box"
        else:
            dy, dx = 10 / 111.32, 10 / (111.32 * math.cos(math.radians(latitude)))
            south, north, west, east = latitude - dy, latitude + dy, longitude - dx, longitude + dx
            kind = "10 km point search envelope"
        if north == south or east == west:
            dy, dx = 10 / 111.32, 10 / (111.32 * math.cos(math.radians(latitude)))
            south, north, west, east = latitude - dy, latitude + dy, longitude - dx, longitude + dx
            kind = "10 km point search envelope"
        if not (-90 <= south < north <= 90 and -180 <= west < east <= 180 and east - west < 180):
            return None
        mrgid = int(row.get("accepted") or row["MRGID"])
        return {
            "name": row["preferredGazetteerName"],
            "mrgid": mrgid,
            "latitude": latitude,
            "longitude": longitude,
            "bounds": [west, south, east, north],
            "source": "marineregions",
            "area_kind": kind,
            "source_url": f"https://www.marineregions.org/gazetteer.php?p=details&id={mrgid}",
            "geometry_wkt": f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))",
        }
    except (KeyError, TypeError, ValueError):
        return None
