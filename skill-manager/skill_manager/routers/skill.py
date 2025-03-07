import datetime
import json
import logging
import os
from datetime import timedelta
from threading import Thread
from typing import Dict, List

import requests_cache
from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from skill_manager import mongo_client
from skill_manager.core.session_cache import SessionCache
from skill_manager.auth_utils import (get_payload_from_token,
                                      get_skill_if_authorized, has_auth_header)
from skill_manager.core import ModelManagementClient
from skill_manager.keycloak_api import KeycloakAPI
from skill_manager.models import Prediction, Skill, SkillType
from skill_manager.routers import client_credentials
from square_auth.auth import Auth
from square_skill_api.models.prediction import QueryOutput
from square_skill_api.models.request import QueryRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skill")

auth = Auth()

session_cache = SessionCache()


@router.get(
    "/{id}",
    response_model=Skill,
)
async def get_skill_by_id(request: Request, id: str = None):
    """Returns the saved skill information."""
    skill = await get_skill_if_authorized(request, skill_id=id, write_access=False)
    logger.debug("get_skill_by_id: {skill}".format(skill=skill))

    return skill


@router.get(
    "",
    response_model=List[Skill],
)
async def get_skills(request: Request):
    """Returns all skills that a user has access to. A user has access to
    all public skills, and private skill created by them."""

    mongo_query = {"published": True}
    if has_auth_header(request):
        payload = await get_payload_from_token(request)
        user_id = payload["username"]
        mongo_query = {"$or": [mongo_query, {"user_id": user_id}]}

    logger.debug("Skill query: {query}".format(query=json.dumps(mongo_query)))
    skills = mongo_client.client.skill_manager.skills.find(mongo_query)
    skills = [Skill.from_mongo(s) for s in skills]

    logger.debug(
        "get_skills: {skills}".format(
            skills=", ".join(["{}:{}".format(s.name, str(s.id)) for s in skills])
        )
    )
    return skills


@router.post(
    "",
    response_model=Skill,
    status_code=201,
)
async def create_skill(
    request: Request,
    skill: Skill,
    keycloak_api: KeycloakAPI = Depends(KeycloakAPI),
    models_client: ModelManagementClient = Depends(ModelManagementClient),
    token_payload: Dict = Depends(auth),
):
    """Creates a new skill and saves it."""

    realm = token_payload["realm"]
    username = token_payload["username"]
    skill.user_id = username

    if skill.created_at is None:
        skill.created_at = datetime.datetime.now()

    client = keycloak_api.create_client(
        realm=realm, username=username, skill_name=skill.name
    )
    skill.client_id = client["clientId"]

    skill_id = mongo_client.client.skill_manager.skills.insert_one(
        skill.mongo()
    ).inserted_id

    skill = await get_skill_by_id(request, skill_id)
    logger.debug("create_skill: {skill}".format(skill=skill))

    # check if the model exists, if not deploy
    has_skill_args = skill.default_skill_args is not None
    if has_skill_args and "base_model" in skill.default_skill_args:
        deploy_thread = Thread(
            target=models_client.deploy_model_if_not_exists,
            args=(skill.default_skill_args,),
        )
        deploy_thread.start()
    else:
        logger.info("No skill_args or no base_model provided. Nothing to deploy.")

    # set the secret *after* saving the skill to mongoDB, so the secret will be
    # returned, but not logged and not persisted.
    skill.client_secret = client["secret"]

    return skill


@router.put("/{id}", response_model=Skill, dependencies=[Depends(auth)])
async def update_skill(
    request: Request,
    id: str,
    data: dict,
    models_client: ModelManagementClient = Depends(ModelManagementClient),
):
    """Updates a skill with the provided data."""
    skill: Skill = await get_skill_if_authorized(
        request, skill_id=id, write_access=True
    )

    for k, v in data.items():
        if hasattr(skill, k):
            setattr(skill, k, v)

    _ = mongo_client.client.skill_manager.skills.find_one_and_update(
        {"_id": ObjectId(id)}, {"$set": data}
    )
    updated_skill: Skill = await get_skill_by_id(request, id)

    # deploy base model if its not running yet
    if updated_skill.default_skill_args:
        deploy_thread = Thread(
            target=models_client.deploy_model_if_not_exists,
            args=(updated_skill.default_skill_args,),
        )
        deploy_thread.start()

    logger.debug(
        "update_skill: old: {skill} updated: {updated_skill}".format(
            skill=skill, updated_skill=updated_skill
        )
    )
    return skill


@router.delete("/{id}", status_code=204, dependencies=[Depends(auth)])
async def delete_skill(request: Request, id: str):
    """Deletes a skill."""
    await get_skill_if_authorized(request, skill_id=id, write_access=True)

    delete_result = mongo_client.client.skill_manager.skills.delete_one(
        {"_id": ObjectId(id)}
    )
    logger.debug("delete_skill: {id}".format(id=id))
    if delete_result.acknowledged:
        return
    else:
        raise RuntimeError(delete_result.raw_result)


@router.post(
    "/{id}/publish",
    response_model=Skill,
    status_code=201,
    dependencies=[Depends(auth)],
)
async def publish_skill(request: Request, id: str):
    """Makes a skill publicly available."""
    skill = await get_skill_if_authorized(request, skill_id=id, write_access=True)
    skill.published = True
    skill = await update_skill(request, id, skill.dict())

    logger.debug("publish_skill: {skill}".format(skill=skill))
    return skill


@router.post(
    "/{id}/unpublish",
    response_model=Skill,
    status_code=201,
    dependencies=[Depends(auth)],
)
async def unpublish_skill(request: Request, id: str):
    """Makes a skill private."""
    skill = await get_skill_if_authorized(request, skill_id=id, write_access=True)
    skill.published = False
    skill = await update_skill(request, id, skill.dict())

    logger.debug("unpublish_skill: {skill}".format(skill=skill))
    return skill


@router.post(
    "/{id}/query",
    response_model=QueryOutput,
)
async def query_skill(
    request: Request,
    query_request: QueryRequest,
    id: str,
    token: str = Depends(client_credentials),
    # sess=Depends(skill_query_session),
):
    """Sends a query to the respective skill and returns its prediction."""
    logger.info(
        "received query: {query} for skill {id}".format(
            query=query_request.json(), id=id
        )
    )

    query = query_request.query
    user_id = query_request.user_id

    skill = await get_skill_if_authorized(request, skill_id=id, write_access=False)
    query_request.skill = json.loads(skill.json())

    default_skill_args = skill.default_skill_args
    if default_skill_args is not None:
        # add default skill args, potentially overwrite with query.skill_args
        query_request.skill_args = {**default_skill_args, **query_request.skill_args}

    # FIXME: Once UI sends context and answers seperatly, this code block can be deleted
    if (
        skill.skill_type == SkillType.multiple_choice
        and "choices" not in query_request.skill_args
    ):
        choices = query_request.skill_args["context"].split("\n")
        if skill.skill_settings.requires_context:
            query_request.skill_args["context"], *choices = choices
        query_request.skill_args["choices"] = choices

    headers = {"Authorization": f"Bearer {token}"}
    if request.headers.get("Cache-Control"):
        headers["Cache-Control"] = request.headers.get("Cache-Control")

    logger.debug(f"query json={query_request.dict()}")
    response = session_cache.session.post(
        f"{skill.url}/query",
        headers=headers,
        json=query_request.dict(),
    )
    if response.status_code > 201:
        logger.exception(response.content)
        response.raise_for_status()
    predictions = QueryOutput.parse_obj(response.json())
    logger.debug(
        "predictions from skill: {predictions}".format(predictions=str(predictions.json())[:100])
    )

    # save prediction to mongodb
    mongo_prediction = Prediction(
        skill_id=skill.id,
        skill_name=skill.name,
        query=query,
        user_id=user_id,
        predictions=predictions.predictions,
    )
    _ = mongo_client.client.skill_manager.predictions.insert_one(
        mongo_prediction.mongo()
    ).inserted_id
    logger.debug(
        "prediction saved {mongo_prediction}".format(
            mongo_prediction=str(mongo_prediction.json())[:100],
        )
    )

    logger.debug(
        "query_skill: query_request: {query_request} predictions: {predictions}".format(
            query_request=query_request.json(), predictions=str(predictions)[:100]
        )
    )
    return predictions
