import logging

from .application import app, db
from flask_httpauth import HTTPBasicAuth
from flask import jsonify, request, abort, g
from .models import App, Study, ParameterInt, ParameterFloat, Scenario, Run
from .common import RunType

auth = HTTPBasicAuth()


def get_scenario(study, scenario):
    study = Study.query.filter_by(name=study, app=g.objfun_app).one_or_none()
    if not study:
        raise LookupError(f'no study {study} for app {g.objfun_app.name}')
    scenario = Scenario.query.filter_by(
        name=scenario, study=study).one_or_none()
    if not scenario:
        raise LookupError(f'no scenario {scenario} for study {study}'
                          f' for app {g.objfun_app.name}')
    return scenario


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
    if not request.get_json():
        abort(400, 'json missing')
    for p in ['name', 'parameters']:
        if p not in request.get_json():
            abort(400, f'{p} missing from json')

    data = request.get_json()
    study = Study(name=data['name'], app=g.objfun_app)
    for p in data['parameters']:
        param = data['parameters'][p]
        if param['type'] == 'int':
            ParameterInt(study=study, name=p,
                         minv=param['minv'], maxv=param['maxv'])
        elif param['type'] == 'float':
            ParameterFloat(study=study, name=p,
                           minv=param['minv'], maxv=param['maxv'],
                           resolution=param['resolution'])
        else:
            msg = f'unknown parameter type {param["type"]}'
            logging.error(msg)
            abort(400, msg)
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
    study = Study.query.filter_by(name=name, app=g.objfun_app).first()
    if not study:
        msg = f'no study {name} for app {g.objfun_app.name}'
        logging.error(msg)
        abort(404, msg)

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
    study = Study.query.filter_by(name=name, app=g.objfun_app).one_or_none()
    if not study:
        msg = f'no study {name} for app {g.objfun_app.name}'
        logging.error(msg)
        abort(404, msg)

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
    if not request.get_json():
        abort(400, 'json missing')
    data = request.get_json()
    for p in ['name', 'runtype']:
        if p not in data:
            abort(400, f'{p} missing from json')
    try:
        runtype = RunType.__members__[data['runtype']]
    except KeyError:
        msg = f'wrong run type {data["runtype"]}'
        logging.error(msg)
        abort(400, msg)

    study = Study.query.filter_by(name=study,
                                  app=g.objfun_app).one_or_none()
    if not study:
        msg = f'no study {data["name"]} for app {g.objfun_app.name}'
        logging.error(msg)
        abort(404, msg)

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

@app.route('/api/studies/<string:study>/scenarios',
           methods=['GET'])
@auth.login_required
def get_all_scenarios(study):
    """get a list of all scenarios of a study
    .. :quickref: studies; get a list of all studies
    :param study: name of the study
    :status 404: when the scenario does not exist
    """

    study = Study.query.filter_by(name=study, app=g.objfun_app).one_or_none()
    if not study:
        msg = f'no study {study} for app {g.objfun_app.name}'
        logging.error(msg)
        abort(404, msg)

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
        scenario = get_scenario(study, name)
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
def get_run(study, name):
    """get a run of a particular scenario
    .. :quickref: studies; get information about a particular run
    :param study: name of the study
    :param name: name of the scenario
    :type name: string
    :status 400: when name or runtype is missing
    :status 404: when the scenario does not exist
    :status 201: the call successfully returned a json string
    """

    if not request.get_json() or 'parameters' not in request.get_json():
        abort(400, 'json missing')
    data = request.get_json()['parameters']

    try:
        scenario = get_scenario(study, name)
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

    if not request.get_json() or 'parameters' not in request.get_json():
        abort(400, 'json missing')
    data = request.get_json()['parameters']

    try:
        scenario = get_scenario(study, name)
    except LookupError as e:
        logging.error(e)
        abort(404, str(e))

    run = scenario.lookup_run(data)
    if isinstance(run, Run):
        result = run.to_dict
    else:
        result = {'status': run}
    return jsonify(result), 201
