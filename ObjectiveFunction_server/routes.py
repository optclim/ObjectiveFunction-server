from .application import app
from flask_httpauth import HTTPBasicAuth
from flask import jsonify, g
from .models import App

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
