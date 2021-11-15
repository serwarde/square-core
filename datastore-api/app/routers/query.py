from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.param_functions import Body, Path, Query

from ..models.httperror import HTTPError
from ..models.query import QueryResult
from .dependencies import get_search_client, get_storage_connector
from .utils import get_fields


router = APIRouter(tags=["Query"])


@router.get(
    "/search",
    summary="Search the documentstore with given query and return top-k documents",
    description="Searches the given datastore with the search strategy specified by the given index \
            and if necessery encodes the query with the specified encoder",
    response_description="The top-K documents",
    response_model=List[QueryResult],
    responses={
        200: {"model": List[QueryResult], "description": "The top-K documents"},
        404: {"model": HTTPError, "description": "The datastore or index does not exist"},
        500: {"model": HTTPError, "description": "Model API error"},
    },
)
async def search(
    datastore_name: str = Path(..., description="Name of the datastore."),
    index_name: Optional[str] = Query(None, description="Index name."),
    query: str = Query(..., description="The query string."),
    top_k: int = Query(40, description="Number of documents to retrieve."),
    conn=Depends(get_storage_connector),
    dense_retrieval=Depends(get_search_client),
):
    # do dense retrieval
    if index_name:
        try:
            return await dense_retrieval.search(datastore_name, index_name, query, top_k)
        except ValueError as ex:
            raise HTTPException(status_code=404, detail=str(ex))
        except Exception as other_ex:
            raise HTTPException(status_code=500, detail=str(other_ex))
    # do sparse retrieval
    else:
        return await conn.search(datastore_name, query, n_hits=top_k)


@router.post(
    "/search_by_vector",
    summary="Search a datastore with the given query vector and return top-k documents",
    description="Searches the given datastore with the search strategy specified by the given index",
    response_description="The top-K documents",
    response_model=List[QueryResult],
    responses={
        200: {"model": List[QueryResult], "description": "The top-K documents"},
        404: {"model": HTTPError, "description": "The datastore or index does not exist"},
        500: {"model": HTTPError, "description": "Model API error"},
    },
)
async def search_by_vector(
    datastore_name: str = Path(..., description="Name of the datastore."),
    index_name: str = Body(..., description="Index name."),
    query_vector: List[float] = Body(..., description="Query vector."),
    top_k: int = Body(40, description="Number of documents to retrieve."),
    conn=Depends(get_storage_connector),
    dense_retrieval=Depends(get_search_client),
):
    # do dense retrieval
    try:
        return await dense_retrieval.search_by_vector(datastore_name, index_name, query_vector, top_k)
    except ValueError as ex:
        raise HTTPException(status_code=404, detail=str(ex))
    except Exception as other_ex:
        raise HTTPException(status_code=500, detail=str(other_ex))


@router.get(
    "/score",
    summary="Score the document with given query",
    description="Scores the document with the given id and the given query and returns the score.",
    response_description="The score",
    # response_model=QueryResultDocument,  # TODO
    responses={
        200: {
            "model": QueryResult,
            "description": "The score between the query and the documnt wiith the given id",
        },
        404: {"model": HTTPError, "description": "The datastore or index does not exist"},
        500: {"model": HTTPError, "description": "Model API error"},
    },
)
async def score(
    datastore_name: str = Path(..., description="Name of the datastore."),
    index_name: Optional[str] = Query(None, description="Index name."),
    query: str = Query(..., description="The query string."),
    doc_id: int = Query(..., description="Document ID to retrieve."),
    conn=Depends(get_storage_connector),
):
    if index_name:
        raise NotImplementedError()
        # TODO do dense retrieval stuff
        # index = await conn.get_index(datastore_name, index_name)
        # if index is None:
        #     raise HTTPException(status_code=404, detail="Datastore or index not found.")
        # try:
        #     query_embedding = encode_query(query, index)
        # except Exception:
        #     raise HTTPException(status_code=500, detail="Model API error.")

    result = await conn.search_for_id(datastore_name, query, doc_id)

    if not result:
        raise HTTPException(status_code=404, detail="Document not found.")
    return result
    # query_embedding_name = Index.get_query_embedding_field_name(index)
    # body = {
    #     "query": query,
    #     "type": "any",
    #     # The only difference compared to the search is the additional filtering by doc_id
    #     "yql": f"select * from sources {datastore_name} where id={doc_id} and ({index.yql_where_clause});",
    #     "ranking.profile": index_name,
    #     f"ranking.features.query({query_embedding_name})": query_embedding,
    # }

    # TODO convert to model object
    # vespa_response = vespa_app.query(body=body)
    # if vespa_response.status_code == 200:
    #     fields = await get_fields(datastore_name)
    #     query_result = QueryResult.from_vespa(vespa_response.json, fields)
    #     # Extract first (and only) document from result if present, otherwise return 404
    #     if len(query_result.documents) > 0:
    #         return query_result.documents[0]
    #     else:
    #         raise HTTPException(status_code=404, detail="Document not found.")
    # else:
    #     raise HTTPException(status_code=500)
