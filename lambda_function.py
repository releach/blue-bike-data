import boto3
import pandas as pd
from rdflib import Graph, Literal, Namespace, RDF, URIRef, RDFS, XSD
from dateutil import parser
import pytz
import io
import zipfile
import urllib.parse


def get_trip_duration(start_date_str, end_date_str):
    start_date = parser.parse(start_date_str)
    end_date = parser.parse(end_date_str)
    duration = end_date - start_date
    return Literal(duration.total_seconds(), datatype=XSD.int)


def transform_date(date_str, input_tz=pytz.timezone('America/New_York')):
    date_obj = parser.parse(date_str)
    date_obj = input_tz.localize(date_obj)
    return Literal(date_obj.isoformat(), datatype=XSD.dateTime)


def bike_rdf(df):
    bike_data = Namespace('https://bluebikes.com/system-data/rdf/bike_data#')
    bike_ontology = Namespace('https://bluebikes.com/system-data/rdf/ontology#')
    bike_taxonomy = Namespace('https://bluebikes.com/system-data/rdf/bike_taxonomy#')
    g = Graph()
    g.bind('bike_ontology', bike_ontology)
    g.bind('bike_taxonomy', bike_taxonomy)
    g.bind('bike_data', bike_data)
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
    for _, row in df.iterrows():
        trip = URIRef(bike_data[row['ride_id']])
        startedAt = transform_date(row['started_at'])
        endedAt = transform_date(row['ended_at'])
        startStation = URIRef(bike_taxonomy[row['start_station_id']])
        endStation = URIRef(bike_taxonomy[row['end_station_id']]) if pd.notnull(row['end_station_id']) else None
        duration = get_trip_duration(row['started_at'], row['ended_at'])
        g.add((trip, RDF.type, bike_ontology.Trip))
        g.add((trip, RDFS.label, Literal(row['ride_id'])))
        g.add((trip, bike_ontology.endedAt, endedAt))
        g.add((trip, bike_ontology.startedAt, startedAt))
        g.add((trip, bike_ontology.startStation, startStation))
        if endStation:
            g.add((trip, bike_ontology.endStation, endStation))
        g.add((trip, bike_ontology.tripDuration, duration))
        g.add((trip, bike_ontology.rideableType, bike_taxonomy.DockedBike))
        g.add((trip, bike_ontology.tripID, Literal(row['ride_id'])))
    output_file_path = '/tmp/output.ttl'
    g.serialize(destination=output_file_path, format='turtle')
    with open(output_file_path, 'r') as file:
        return file.read()


def lambda_handler(event, context):
    s3 = boto3.client('s3')
    output_bucket_name = 'csv-out-for-ttl'
    filename = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])
    input_bucket_name = event['Records'][0]['s3']['bucket']['name']
    zip_object = s3.get_object(Bucket=input_bucket_name, Key=filename)
    zip_file_content = zip_object['Body'].read()
    expected_csv_filename = filename.replace('.zip', '.csv')
    with zipfile.ZipFile(io.BytesIO(zip_file_content), 'r') as zip_ref:
        csv_files = [f for f in zip_ref.namelist() if f == expected_csv_filename]
        if not csv_files:
            raise Exception(f"Expected CSV file {expected_csv_filename} not found in the ZIP.")
        csv_file_like_object = io.StringIO(zip_ref.read(csv_files[0]).decode('utf-8'))
    df = pd.read_csv(csv_file_like_object, nrows=300)
    output_ttl_content = bike_rdf(df)
    output_filename = expected_csv_filename.replace('.csv', '.ttl')
    s3.put_object(Bucket=output_bucket_name, Key=output_filename, Body=output_ttl_content)
