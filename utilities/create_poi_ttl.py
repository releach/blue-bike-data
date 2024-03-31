import osmnx as ox
import pandas as pd
import pandas as pd
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

""" Get POI data from the OSM API and convert it to TTL. """


def fetch_pois(place, tags):
    """
    Get POIs in the city of Boston, along wtih lat/long, websites, and types. 
    """
    pois = ox.features_from_place(place, tags=tags)
    return pois

def extract_lat_lon(pois, tags):
    """
    Extract latitude, longitude, POI type, and URL, handling non-point geometries
    and skipping entries without a location.
    """
    latitudes = []
    longitudes = []
    names = []
    types = []
    websites = []  

    for _, row in pois.iterrows():
        geom = row.geometry
        poi_type = None
        for tag_key, tag_values in tags.items():
            if isinstance(tag_values, list):
                for value in tag_values:
                    if tag_key in row and row[tag_key] == value:
                        poi_type = f"{tag_key}={value}"
                        break
            elif tag_values is True and tag_key in row:
                poi_type = f"{tag_key}={row[tag_key]}"
            
            if poi_type:
                break
        
        if poi_type and geom:
            if geom.geom_type == 'Point':
                latitudes.append(geom.y)
                longitudes.append(geom.x)
                names.append(row.get('name', None))
                types.append(poi_type)
                websites.append(row.get('website', None))  
            elif geom.geom_type in ['Polygon', 'MultiPolygon', 'LineString', 'MultiLineString']:
                latitudes.append(geom.centroid.y)
                longitudes.append(geom.centroid.x)
                names.append(row.get('name', None))
                types.append(poi_type)
                websites.append(row.get('website', None)) 

    return names, latitudes, longitudes, types, websites



def get_pois():
"""
Pull down POI data from the OSM API. 
"""
    place = "Boston, MA, USA"
    tags = {
        'amenity': ['library'], # Libraries; 
        'tourism': ['museum'], # Museums; 
        'historic': True  # Other historic sites
    }

    pois = fetch_pois(place, tags)
    
    names, latitudes, longitudes, types, websites = extract_lat_lon(pois, tags)
    
    pois_filtered = pd.DataFrame({
        'name': names,
        'latitude': latitudes,
        'longitude': longitudes,
        'type': types,
        'website': websites
    })
    
    # We don't want POIs without locations so we drop those
    pois_filtered.dropna(subset=['name', 'latitude', 'longitude', 'type'], inplace=True)
    pois_filtered.reset_index(drop=True, inplace=True)

    return pois_filtered

def create_ttl(poi_data):
"""
Create TTL file from POI dataframe. 
"""
    df = poi_data

    SCHEMA = Namespace("http://schema.org/")
    GEO = Namespace("http://www.opengis.net/ont/geosparql#")
    POI_DATA = Namespace("https://bluebikes.com/system-data/rdf/poi_data#")

    g = Graph()

    g.bind("schema", Namespace("http://schema.org/"), replace=True)
    g.bind("geo", GEO)
    g.bind("poi_data", POI_DATA)

    def map_type_to_class(type_value):
        if type_value == "tourism=museum":
            return SCHEMA.Museum
        elif type_value.startswith("amenity=library"):
            return SCHEMA.Library
        else:
            return SCHEMA.LandmarksOrHistoricalBuildings

    for index, row in df.iterrows():
        poi_uri = URIRef(POI_DATA[str(index).zfill(5)]) 
        
        g.add((poi_uri, RDF.type, map_type_to_class(row['type'])))
        
        g.add((poi_uri, RDFS.label, Literal(row['name'])))
        
        if not pd.isnull(row['website']) and row['website'] != '':
            g.add((poi_uri, SCHEMA.url, URIRef(row['website'])))
        
        point = Literal(f"POINT({row['longitude']} {row['latitude']})", datatype=GEO.wktLiteral)
        g.add((poi_uri, GEO.asWKT, point)) # For simplicity, associated asWKT prop directly with POI

    turtle_data = g.serialize(format="turtle")
    with open('poi_data_combined.ttl', 'w') as f:
        f.write(turtle_data)
    print("Wrote .ttl file to your working directory.")



def main():
    poi_data = get_pois()
    create_ttl(poi_data)

if __name__ == "__main__":
    main()
