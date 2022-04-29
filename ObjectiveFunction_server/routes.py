import logging

from .application import app, db
from flask_httpauth import HTTPBasicAuth
from flask import jsonify, request, abort, g
from .models import App, Study

auth = HTTPBasicAuth()


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
    :status 400: when name is missing
    :status 409: when study already exists
    """
    if not request.get_json() or 'name' not in request.get_json():
        abort(400)

    data = request.get_json()
    study = Study(name=data['name'], app=g.objfun_app)
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
    :query info: request particular information about the study.
    :status 404: when the study does not exist
    :status 404: when unkown information is requested
    :status 200: the call successfully returned a json string
    """
    study = Study.query.filter_by(name=name, app=g.objfun_app).first()
    if not study:
        logging.error(f'no study {name} for app {g.objfun_app.name}')
        abort(404)

    return jsonify(study.to_dict), 200
