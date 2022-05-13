import logging

from .application import app, db
from flask_httpauth import HTTPBasicAuth
from flask import jsonify, request, abort, g
from .models import App, Study, Scenario, Run, ObsName
from .common import RunType, LookupState

auth = HTTPBasicAuth()


def check_json(data, required_keys=[]):
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
    :status 400: when name or parameters is missing
    :status 409: when study already exists
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


@app.route('/api/studies/<string:name>', methods=['GET'])
@auth.login_required
def get_study(name):
    """get information about a particular study
    .. :quickref: studies; get information about a particular study
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

    return jsonify(study.to_dict), 200


@app.route('/api/studies/<string:name>/parameters', methods=['GET'])
@auth.login_required
def get_study_params(name):
    """get information about a particular study
    .. :quickref: studies; get information about a particular study
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
    """create a new study
    .. :quickref: create_scenario; create a new scenario for study
    :param name: name of the study
    :<json string name: the name of the scenario
    :status 400: when name or runtype is missing
    :status 404: when the study does not exist
    :status 409: when scenario already exists
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
    :param study: name of the study
    :status 404: when the scenario does not exist
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
    :status 404: when the scenario does not exist
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


@app.route('/api/studies/<string:study>/scenarios/<string:name>/runs',
           methods=['GET'])
@auth.login_required
def get_all_runs(study, name):
    """get all runs of a particular scenario
    .. :quickref: studies; get information about a particular scenario
    :param study: name of the study
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
    .. :quickref: studies; get information about a particular run
    :param study: name of the study
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
    .. :quickref: studies; get information about a particular scenario
    :param study: name of the study
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
