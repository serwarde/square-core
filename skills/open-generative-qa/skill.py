import logging

from square_skill_api.models import QueryOutput, QueryRequest

from square_skill_helpers import ModelAPI, DataAPI

logger = logging.getLogger(__name__)

model_api = ModelAPI()
data_api = DataAPI()


async def predict(request: QueryRequest) -> QueryOutput:
    """Given a question and context, performs extractive QA. This skill is a general
    skill, it can be used with any adapter for extractive question answering. The
    adapter to use can be specified in the `skill_args` or via the `default_skill_args`
    in the skill-manager.
    """

    query = request.query
    explain_kwargs = request.explain_kwargs or {}

    data = await data_api(
        datastore_name=request.skill_args["datastore"],
        index_name=request.skill_args.get("index", ""),
        query=query,
    )
    logger.info(f"Data API output:\n{data}")
    context = [d["document"]["text"] for d in data]
    context_score = [d["score"] for d in data]

    # prepared_input = [[query, c] for c in context]
    # model_request = {
    #     "input": prepared_input,
    #     "task_kwargs": {"topk": request.skill_args.get("topk", 5)},
    #     "explain_kwargs": explain_kwargs,
    # }
    # if request.skill_args.get("adapter"):
    #     model_request["adapter_name"] = request.skill_args["adapter"]
    # model_api_output = await model_api(
    #     model_name=request.skill_args["base_model"],
    #     pipeline="question-answering",
    #     model_request=model_request,
    # )

    query_context_seperator = request.skill_args.get("query_context_seperator", " ")
    prepared_input = [[query + query_context_seperator + c] for c in context]

    model_request = {
        "input": prepared_input,
        "model_kwargs": {
            "output_scores": True,
            **request.skill_args.get("model_kwargs", {}),
        },
        "explain_kwargs": explain_kwargs,
    }
    if request.skill_args.get("adapter"):
        model_request["adapter_name"] = request.skill_args["adapter"]

    model_api_output = await model_api(
        model_name=request.skill_args["base_model"],
        pipeline="generation",
        model_request=model_request,
    )
    logger.info(f"Model API output:\n{model_api_output}")

    return QueryOutput.from_generation(
        model_api_output=model_api_output, context=context
    )
