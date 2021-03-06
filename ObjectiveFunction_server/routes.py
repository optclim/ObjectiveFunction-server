import logging

from .application import app, db
from flask_httpauth import HTTPBasicAuth
from flask import jsonify, request, abort, g
from .models import App, Study, Scenario, Run, ObsName
from .common import RunType, LookupState

auth = HTTPBasicAuth()


def check_json(data, required_keys=[]):
    """check if json object valid

    :param data: the json object to be checked
    :param required_keys: list of keys that must be present in data object
    :type required_keys: list
    """
    if not data:
        raise RuntimeError('json missing')
    for k in required_keys:
        if k not in data:
            raise RuntimeError(f'parameter {k} missing from json')
    return data


@auth.verify_password
def verify_password(name_or_token, password):
    # first try to authenticate by token
    objfun_app = App.verify_auth_token(name_or_token)
    if not objfun_app:
        # try to authenticate with name/password
        objfun_app = App.query.filter_by(name=name_or_token).first()
        if not objfun_app or not objfun_app.verify_password(password):
            return False
    g.objfun_app = objfun_app
    return True


@app.route('/api/token')
@auth.login_required
def get_auth_token():
    """get the authentication token

    .. :quickref: token; get the authentication token

    :>json string token: the authentication token
    """
    token = g.objfun_app.generate_auth_token()
    return jsonify({'token': token.decode('ascii')})


@app.route('/api/studies', methods=['GET'])
@auth.login_required
def get_all_studies():
    """get a list of all studies

    .. :quickref: studies; get a list of all studies

    :>jsonarr int id: study ID
    :>jsonarr string name: study name
    :>jsonarr string app: app name
    :>jsonarr int num_scenarios: the number of scenarios associated
                                 with this study
    """
    results = []
    for study in g.objfun_app.studies:
        results.append(study.to_dict)
    return jsonify({'data': results}), 200


@app.route('/api/create_study', methods=['POST'])
@auth.login_required
def create_study():
    """create a new study

    .. :quickref: create_study; create a new study

    :<json string name: the name of the study
    :<json list parameters: a list of parameters associated with study
    :>json int id: study ID
    :>json string name: study name
    :>json string app: app name
    :>json int num_scenarios: the number of scenarios associated
                                 with this study
    :status 400: when name or parameters is missing
    :status 409: when study already exists
    :status 201: study was successfully created
    """
    try:
        data = check_json(request.get_json(), ['name', 'parameters'])
    except RuntimeError as e:
        abort(400, str(e))

    study = Study(name=data['name'], app=g.objfun_app)
    for pname in data['parameters']:
        try:
            study.add_parameter(pname, data['parameters'][pname])
        except RuntimeError as e:
            logging.error(e)
            abort(400, str(e))
    db.session.add(study)
    db.session.commit()

    return jsonify(study.to_dict), 201


@app.route('/api/studies/<string:name>', methods=['GET', 'DELETE'])
@auth.login_required
def get_study(name):
    """
    .. :quickref: studies; get study
    .. http:get:: /api/studies/(string:name)

    get information about a particular stud

    :param name: name of the study
    :type name: string
    :status 404: when the study does not exist
    :status 200: the call successfully returned a json string
    :>json int id: study ID
    :>json string name: study name
    :>json string app: app name
    :>json int num_scenarios: the number of scenarios associated
                                 with this study

    .. :quickref: studies; delete study
    .. http:delete:: /api/studies/(string:name)

    delete a study

    :param name: name of the study
    :type name: string
    :status 404: when the study does not exist
    :status 200: the study was successfully deleted
    """
    try:
        study = g.objfun_app.get_study(name)
    except LookupError as e:
        logging.error(e)
        abort(404, str(e))

    if request.method == 'GET':
        res = jsonify(study.to_dict)
    elif request.method == 'DELETE':
        db.session.delete(study)
        db.session.commit()
        res = ''
    return res, 200


@app.route('/api/studies/<string:name>/parameters', methods=['GET'])
@auth.login_required
def get_study_params(name):
    """get study parameters

    .. :quickref: studies; get study parameters

    :param name: name of the study
    :type name: string
    :status 404: when the study does not exist
    :status 200: the call successfully returned a json string
    """
    try:
        study = g.objfun_app.get_study(name)
    except LookupError as e:
        logging.error(e)
        abort(404, str(e))

    params = {}
    for p in study.parameters:
        params[p.name] = p.to_dict

    return jsonify(params), 200


@app.route('/api/studies/<string:study>/create_scenario', methods=['POST'])
@auth.login_required
def create_scenario(study):
    """create a new scenario

    .. :quickref: studies; create a new scenario for study

    :param name: name of the study
    :type name: string

    :<json string name: the name of the scenario
    :<json string runtype: the type of scenrio, must be one of 'MISFIT', 'PATH'
    :status 400: when name or runtype is missing
    :status 404: when the study does not exist
    :status 409: when scenario already exists
    :status 201: the scenario was successfully created
    """
    try:
        data = check_json(request.get_json(), ['name', 'runtype'])
    except RuntimeError as e:
        abort(400, str(e))

    try:
        runtype = RunType.__members__[data['runtype']]
    except KeyError:
        msg = f'wrong run type {data["runtype"]}'
        logging.error(msg)
        abort(400, msg)

    try:
        study = g.objfun_app.get_study(study)
    except LookupError as e:
        logging.error(e)
        abort(404, str(e))

    # check if scenario already exists
    scenario = Scenario.query.filter_by(
        study=study, name=data['name']).one_or_none()
    if scenario:
        msg = f'scenario {data["name"]} already exists'
        logging.warning(msg)
        abort(409, msg)

    scenario = Scenario(study=study, name=data['name'], runtype=runtype)
    db.session.add(scenario)
    db.session.commit()

    return '', 201


@app.route('/api/studies/<string:study>/observation_names',
           methods=['PUT', 'GET'])
@auth.login_required
def observation_names(study):
    """get/set list of observation names of a study

    .. :quickref: studies; get/set list of observation names of a study

    :param study: name of the study
    :type study: string

    :status 404: when the study does not exist or the observation names do
                 not match
    :status 200: list of observation names
    :status 201: observation names were successfully added
    """
    try:
        study = g.objfun_app.get_study(study)
    except LookupError as e:
        logging.error(e)
        abort(404, str(e))

    if request.method == 'GET':
        obsnames = []
        for o in study.obsnames:
            obsnames.append(o.name)
        return jsonify({'obsnames': obsnames}), 200
    elif request.method == 'PUT':
        try:
            data = check_json(request.get_json(), ['obsnames'])
        except RuntimeError as e:
            abort(400, str(e))
        obsnames = data['obsnames']
        if len(study.obsnames) > 0:
            # check names
            if len(obsnames) != len(study.obsnames):
                msg = 'number of observation names does not match'
                logging.error(msg)
                abort(404, msg)
            error = False
            for o in study.obsnames:
                if o.name not in obsnames:
                    logging.error(f'{o.name} missing')
                    error = True
            if error:
                msg = 'observation names do not match'
                logging.error(msg)
                abort(404, msg)
        else:
            for o in obsnames:
                db.session.add(ObsName(name=o, study=study))
            db.session.commit()
            return '', 201


@app.route('/api/studies/<string:study>/scenarios',
           methods=['GET'])
@auth.login_required
def get_all_scenarios(study):
    """get a list of all scenarios of a study

    .. :quickref: studies; get a list of all studies

    :param study: name of the study
    :type study: string
    :status 404: when the scenario does not exist
    :status 200: studies
    """

    try:
        study = g.objfun_app.get_study(study)
    except LookupError as e:
        logging.error(e)
        abort(404, str(e))

    results = []
    for scenario in study.scenarios:
        results.append(scenario.to_dict)
    return jsonify({'data': results}), 200


@app.route('/api/studies/<string:study>/scenarios/<string:name>',
           methods=['DELETE'])
@auth.login_required
def delete_scenario(study, name):
    """delate a scenario including all associated runs

    .. :quickref: scenarios; delete scenario

    :param study: name of the study
    :type study: string
    :param name: name of the scenario
    :type name: string
    :status 404: when the scenario does not exist
    :status 200: the call successfully deleted the scenario
    """

    try:
        scenario = g.objfun_app.get_scenario(study, name)
    except LookupError as e:
        logging.error(e)
        abort(404, str(e))

    db.session.delete(scenario)
    db.session.commit()

    return '', 200


@app.route('/api/studies/<string:study>/scenarios/<string:name>/runs',
           methods=['GET'])
@auth.login_required
def get_all_runs(study, name):
    """get all runs of a particular scenario

    .. :quickref: scenarios; get information about a particular scenario

    :param study: name of the study
    :type study: string
    :param name: name of the scenario
    :type name: string
    :status 404: when the scenario does not exist
    :status 200: the call successfully returned a json string
    """

    try:
        scenario = g.objfun_app.get_scenario(study, name)
    except LookupError as e:
        logging.error(e)
        abort(404, str(e))

    results = []
    for run in scenario.runs:
        results.append(run.to_dict)
    return jsonify({'data': results}), 200


@app.route('/api/studies/<string:study>/scenarios/<string:name>/get_run',
           methods=['POST'])
@auth.login_required
def get_run_by_params(study, name):
    """get a run of a particular scenario

    .. :quickref: scenarios; get information about a particular run

    :param study: name of the study
    :type study: string
    :param name: name of the scenario
    :type name: string
    :status 400: when name or runtype is missing
    :status 404: when the scenario does not exist
    :status 201: the call successfully returned a json string
    """

    try:
        data = check_json(request.get_json(), ['parameters'])
    except RuntimeError as e:
        abort(400, str(e))
    data = data['parameters']

    try:
        scenario = g.objfun_app.get_scenario(study, name)
    except LookupError as e:
        logging.error(e)
        abort(404, str(e))

    try:
        run = scenario.get_run(data)
    except LookupError:
        abort(404, 'no such run')

    return jsonify(run.to_dict), 201

@app.route('/api/studies/<string:study>/scenarios/<string:name>/lookup_run',
           methods=['POST'])
@auth.login_required
def lookup_run(study, name):
    """lookup a run of a particular scenario

    .. :quickref: scenarios; lookup run

    :param study: name of the study
    :type study: string
    :param name: name of the scenario
    :type name: string
    :status 400: when name or runtype is missing
    :status 404: when the scenario does not exist
    :status 201: the call successfully returned a json string
    """

    try:
        data = check_json(request.get_json(), ['parameters'])
    except RuntimeError as e:
        abort(400, str(e))
    data = data['parameters']

    try:
        scenario = g.objfun_app.get_scenario(study, name)
    except LookupError as e:
        logging.error(e)
        abort(404, str(e))

    run = scenario.lookup_run(data)
    if isinstance(run, Run):
        result = run.to_dict
    else:
        result = {'status': run}
    return jsonify(result), 201


@app.route(
    '/api/studies/<string:study>/scenarios/<string:name>/runs/with_state',
    methods=['POST'])
@auth.login_required
def get_run_with_state(study, name):  # noqa: 318
    """get run in a particular state

    .. :quickref: runs; get run in particular state

    :param study: name of the study
    :type study: string
    :param name: name of the scenario
    :type name: string
    :<json string state: the state the run should be in
    :<json string new_state: optionally, the new state the run will move to
    :status 400: when name or runtype is missing
    :status 404: when the scenario does not exist
    :status 201: the call successfully returned a json string
    """
    try:
        data = check_json(request.get_json(), ['state'])
    except RuntimeError as e:
        abort(400, str(e))

    try:
        state = LookupState.__members__[data['state']]
    except KeyError:
        msg = f'unkown state {data["state"]}'
        logging.error(msg)
        abort(400, msg)
    new_state = None
    if 'new_state' in data:
        try:
            new_state = LookupState.__members__[data['new_state']]
        except KeyError:
            msg = f'unkown state {data["new_state"]}'
            logging.error(msg)
            abort(400, msg)

    try:
        scenario = g.objfun_app.get_scenario(study, name)
    except LookupError as e:
        logging.error(e)
        abort(400, str(e))

    try:
        run = scenario.get_run_with_state(state, new_state)
    except LookupError as e:
        logging.error(e)
        abort(404, str(e))

    result = run.to_dict
    result['values'] = run.values_to_dict

    return jsonify(result), 201


@app.route(
    '/api/studies/<string:study>/scenarios/<string:name>/runs/<int:runid>',
    methods=['GET'])
@auth.login_required
def get_run_by_id(study, name, runid):
    """get run info by id

    .. :quickref: runs; get run by ID

    :param study: name of the study
    :type study: string
    :param name: name of the scenario
    :type name: string
    :param id: the run ID
    :type id: int
    :status 404: when the run does not exist
    :status 200: json object containing run
    """
    try:
        run = g.objfun_app.get_run(study, name, runid)
    except LookupError as e:
        logging.error(e)
        abort(404, str(e))

    return jsonify(run.to_dict), 200


@app.route(
    '/api/studies/<string:study>/scenarios/<string:name>/runs/'
    '<int:runid>/state',
    methods=['GET', 'PUT'])
@auth.login_required
def run_state(study, name, runid):
    """get/set run state

    .. :quickref: runs; get/set run state

    :param study: name of the study
    :type study: string
    :param name: name of the scenario
    :type name: string
    :param id: the run ID
    :type id: int
    :status 404: when the run does not exist
    """
    try:
        run = g.objfun_app.get_run(study, name, runid)
    except LookupError as e:
        logging.error(e)
        abort(404, str(e))

    if request.method == 'GET':
        return jsonify({'state': run.state.name}), 200
    elif request.method == 'PUT':
        try:
            data = check_json(request.get_json(), ['state'])
        except RuntimeError as e:
            abort(400, str(e))
        try:
            state = LookupState.__members__[data['state']]
        except KeyError:
            msg = f'unkown state {data["state"]}'
            logging.error(msg)
            abort(400, msg)
        run.state = state
        db.session.commit()
        return '', 201


@app.route(
    '/api/studies/<string:study>/scenarios/<string:name>/runs/'
    '<int:runid>/value',
    methods=['GET', 'PUT'])
@auth.login_required
def run_value(study, name, runid):  # noqa: C901
    """get/set run value

    .. :quickref: runs; get/set run value

    :param study: name of the study
    :type study: string
    :param name: name of the scenario
    :type name: string
    :param id: the run ID
    :type id: int
    :status 404: when the run does not exist
    """
    try:
        run = g.objfun_app.get_run(study, name, runid)
    except LookupError as e:
        logging.error(e)
        abort(404, str(e))

    if request.method == 'GET':
        return jsonify(run.get_value()), 200
    elif request.method == 'PUT':
        try:
            data = check_json(request.get_json())
        except RuntimeError as e:
            abort(400, str(e))
        force = False
        if 'force' in data:
            force = data['force']
        try:
            run.set_value(data, force=force)
        except KeyError as e:
            abort(400, str(e))
        except RuntimeError as e:
            abort(403, str(e))
        return '', 201
