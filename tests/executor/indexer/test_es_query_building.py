import pytest

from now.executor.indexer.elastic.elastic_indexer import lift_chunk_chunks_to_chunks
from now.executor.indexer.elastic.es_query_building import (
    build_es_queries,
    generate_score_calculation,
    process_filter,
)


def test_generate_score_calculation(es_inputs):
    """
    This test tests the generate_score_calculation function from es_query_building.
    It should return a list of score calculation, with comparisons between
    all query field + search field combinations that are in the same vector space (same encoder)
    and assign the default linear weight of 1.
    """
    (
        index_docs_map,
        query_docs_map,
        document_mappings,
        default_score_calculation,
        _,
    ) = es_inputs
    document_mappings = document_mappings[0]
    encoder_to_fields = {document_mappings[0]: document_mappings[2]}
    default_score_calculation = default_score_calculation[
        :-1
    ]  # omit the last score calculation, contains bm25
    score_calculation = generate_score_calculation(query_docs_map, encoder_to_fields)
    assert score_calculation == default_score_calculation


def test_build_es_queries_default(es_inputs):
    """
    This test tests the build_es_queries function es_query_building.
    It should return a list of ES queries, with cosine comparisons between
    all query-doc field pairs that are in the same vector space (same encoder)
    and assign the same linear weight of 1.
    """
    (
        index_docs_map,
        query_docs_map,
        document_mappings,
        default_score_calculation,
        _,
    ) = es_inputs
    lift_chunk_chunks_to_chunks(query_docs_map)
    _, es_query = build_es_queries(
        docs_map=query_docs_map,
        get_score_breakdown=False,
        score_calculation=default_score_calculation,
    )[0]
    es_query['knn'][0].pop('query_vector')
    es_query['knn'][1].pop('query_vector')
    print(es_query)
    assert es_query == {
        'knn': [
            {
                'field': 'title-clip.embedding',
                'k': 10,
                'num_candidates': 100,
                'boost': 1.0,
            },
            {
                'field': 'gif-clip.embedding',
                'k': 10,
                'num_candidates': 100,
                'boost': 1.0,
            },
        ],
        'query': {
            'bool': {
                'should': [{'multi_match': {'query': 'cat', 'fields': ['title^10']}}]
            }
        },
    }


def test_build_es_queries_filters(es_inputs):
    (
        index_docs_map,
        query_docs_map,
        document_mappings,
        default_score_calculation,
        _,
    ) = es_inputs
    lift_chunk_chunks_to_chunks(query_docs_map)

    # test adding categorical filters
    filters = {'tags__color': ['red', 'blue']}
    _, es_query = build_es_queries(
        docs_map=query_docs_map,
        get_score_breakdown=False,
        score_calculation=default_score_calculation,
        filter=filters,
    )[0]
    es_query['knn'][0].pop('query_vector')
    es_query['knn'][1].pop('query_vector')
    assert es_query == {
        'knn': [
            {
                'field': 'title-clip.embedding',
                'k': 10,
                'num_candidates': 100,
                'boost': 1.0,
                'filter': [{'terms': {'tags.color': ['red', 'blue']}}],
            },
            {
                'field': 'gif-clip.embedding',
                'k': 10,
                'num_candidates': 100,
                'boost': 1.0,
                'filter': [{'terms': {'tags.color': ['red', 'blue']}}],
            },
        ],
        'query': {
            'bool': {
                'should': [{'multi_match': {'query': 'cat', 'fields': ['title^10']}}]
            }
        },
    }

    # test adding text filters
    filters = {'tags__color': 'red'}
    _, es_query = build_es_queries(
        docs_map=query_docs_map,
        get_score_breakdown=False,
        score_calculation=default_score_calculation,
        filter=filters,
    )[0]
    es_query['knn'][0].pop('query_vector')
    es_query['knn'][1].pop('query_vector')
    assert es_query == {
        'knn': [
            {
                'field': 'title-clip.embedding',
                'k': 10,
                'num_candidates': 100,
                'boost': 1.0,
                'filter': [{'match': {'tags.color.text_search': 'red'}}],
            },
            {
                'field': 'gif-clip.embedding',
                'k': 10,
                'num_candidates': 100,
                'boost': 1.0,
                'filter': [{'match': {'tags.color.text_search': 'red'}}],
            },
        ],
        'query': {
            'bool': {
                'should': [{'multi_match': {'query': 'cat', 'fields': ['title^10']}}]
            }
        },
    }


TEST_FILTERS = [
    ({'tags__price': {'gt': 10, 'lt': 100}}, None),
    ({'tags__price': {'gt': 10}}, None),
    ({'tags__price': {'lte': 10}, 'tags__color': ['green', 'blue']}, None),
    ({'tags__color': ['red', 'blue']}, None),
    ({'tags__color': 'red'}, None),
    ({'tags__color': 5}, ValueError),
]


@pytest.mark.parametrize(
    ("filters", "error"),
    TEST_FILTERS,
)
def test_filter_processing(filters, error):
    """
    This test tests the process_filter function from es_query_building, including an errorful filter case.
    """
    if error:
        with pytest.raises(error):
            process_filter(filters)
    else:
        processed_filters = process_filter(filters)
        assert list(processed_filters[0].keys())[0].count("__") == 0
