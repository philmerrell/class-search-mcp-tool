"""
Test script to verify OpenSearch connection.
Run this locally to confirm connectivity before integrating into MCP tool.

Usage:
    python test_opensearch.py
"""

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth


def get_opensearch_client():
    """Create an OpenSearch client using AWS IAM auth."""
    # Use the dev-ai profile for local testing
    session = boto3.Session(profile_name='dev-ai')
    credentials = session.get_credentials()

    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        'us-west-2',
        'es',
        session_token=credentials.token
    )

    client = OpenSearch(
        hosts=[{
            'host': 'search-opensearch-dev-01-t4a3j3mz3m5zedfbx2tnhkd2oi.us-west-2.es.amazonaws.com',
            'port': 443
        }],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection
    )

    return client


def test_connection():
    """Test basic connectivity to OpenSearch."""
    print("Connecting to OpenSearch...")
    client = get_opensearch_client()

    # Test cluster health
    print("\n--- Cluster Health ---")
    health = client.cluster.health()
    print(f"Cluster: {health['cluster_name']}")
    print(f"Status: {health['status']}")
    print(f"Nodes: {health['number_of_nodes']}")

    # List available indices
    print("\n--- Available Indices ---")
    indices = client.cat.indices(format='json')
    class_indices = [idx for idx in indices if 'classes' in idx['index']]
    for idx in class_indices[:10]:  # Show first 10
        print(f"  {idx['index']} - {idx['docs.count']} docs")

    return client


def test_basic_query(client):
    """Run a basic search query."""
    print("\n--- Basic Search Query ---")
    print("Searching for Computer Science classes in Spring 2026 (1263)...")

    response = client.search(
        index='1263_classes_current',
        body={
            'query': {
                'match': {
                    'SubjectDescription': 'Computer Science'
                }
            },
            'size': 5
        }
    )

    total = response['hits']['total']['value']
    print(f"Found {total} total results. Showing first 5:\n")

    for hit in response['hits']['hits']:
        course = hit['_source']
        subject = course.get('Subject', '')
        catalog = course.get('CatalogNumber', '')
        title = course.get('ClassTitle', course.get('courseTitle', ''))
        instructor = course.get('InstructorName', 'TBA')
        print(f"  {subject} {catalog}: {title}")
        print(f"    Instructor: {instructor}")
        print()


def test_aggregation(client):
    """Test an aggregation query to show OpenSearch capabilities."""
    print("\n--- Aggregation Query ---")
    print("Getting top 10 subjects by class count for Spring 2026...")

    response = client.search(
        index='1263_classes_current',
        body={
            'size': 0,  # We only want aggregations, not documents
            'aggs': {
                'subjects': {
                    'terms': {
                        'field': 'Subject.keyword',
                        'size': 10
                    }
                }
            }
        }
    )

    buckets = response['aggregations']['subjects']['buckets']
    print(f"\nTop subjects by number of class sections:")
    for bucket in buckets:
        print(f"  {bucket['key']}: {bucket['doc_count']} sections")


def inspect_document_structure(client):
    """Inspect the structure of a class document."""
    print("\n--- Document Structure ---")
    print("Fetching a sample document to inspect available fields...")

    response = client.search(
        index='1263_classes_current',
        body={
            'query': {'match_all': {}},
            'size': 1
        }
    )

    if response['hits']['hits']:
        doc = response['hits']['hits'][0]['_source']
        print("\nAvailable fields in class documents:")
        for key in sorted(doc.keys()):
            value = doc[key]
            value_preview = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
            print(f"  {key}: {value_preview}")


if __name__ == '__main__':
    try:
        client = test_connection()
        test_basic_query(client)
        test_aggregation(client)
        inspect_document_structure(client)
        print("\n✓ All tests passed! OpenSearch connection is working.")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise
