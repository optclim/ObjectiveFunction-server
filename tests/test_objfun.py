from flask_testing import TestCase as FlaskTestCase
from unittest import TestCase
import base64

from ObjectiveFunction_server import app, db
from ObjectiveFunction_server.models import App, Study, Scenario, ObsName
from ObjectiveFunction_server.models import RunMisfit, RunPath
from ObjectiveFunction_server.common import RunType, LookupState
from ObjectiveFunction_server.routes import check_json

# test data
app_name = 'test'
passwd = 'testpw'
study_name = 'test study'
param_float = {'type': 'float',
               'minv': -10.,
               'maxv': 10.,
               'resolution': 0.1}
param_int = {'type': 'int',
             'minv': 10,
             'maxv': 100}
test_parameters = {'paramA': param_float, 'paramB': param_int}
scenario_misfit_name = 'scenario misfit'
scenario_path_name = 'scenario path'
run_misfit = ({'paramA': 0, 'paramB': 50}, 10.)
run_path = ({'paramA': 0, 'paramB': 50}, '/some/path')

headers = {}
headers['Authorization'] = 'Basic ' + base64.b64encode(
    (app_name + ':' + passwd).encode('utf-8')).decode('utf-8')


class CheckJson(TestCase):
    def test_check_json_fail(self):
        with self.assertRaises(RuntimeError):
            check_json(None)

    def test_check_json_missing_key(self):
        with self.assertRaises(RuntimeError):
            check_json({'hello': 'test'}, required_keys=['not', 'here'])


class ObjFunBase(FlaskTestCase):

    def create_app(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"

        # pass in test configuration
        return app

    def setUp(self):
        self.app = app.test_client()

        db.create_all()
        # create app
        a = App(name=app_name)
        a.hash_password(passwd)
        db.session.add(a)
        # create study
        st = Study(name=study_name, app=self.get_app())
        # and some parameters
        for p in test_parameters:
            st.add_parameter(p, test_parameters[p])
        # add scenarios
        Scenario(name=scenario_misfit_name, runtype=RunType.MISFIT, study=st)
        Scenario(name=scenario_path_name, runtype=RunType.PATH, study=st)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()

    def get_app(self):
        app = App.query.filter_by(name=app_name).first()
        return app


class ObjFunModel(ObjFunBase):

    def test_app(self):
        a = 'test2'
        p = 'testing'
        a = App(name=a)
        a.hash_password(p)
        self.assertTrue(a.verify_password(p))
        self.assertFalse(a.verify_password(p + 'not'))

        db.session.add(a)
        db.session.commit()

        assert a in db.session

    def test_get_study_fail(self):
        with self.assertRaises(LookupError):
            self.get_app().get_study(study_name + 'fail')

    def test_get_study(self):
        study = self.get_app().get_study(study_name)
        self.assertEqual(
            study.to_dict,
            {'id': study.id,
             'name': study_name,
             'app': app_name,
             'num_scenarios': 2})

    def test_add_parameter_fail(self):
        st = Study(name='test', app=self.get_app())
        # no parameter type
        with self.assertRaises(RuntimeError):
            st.add_parameter('test_p', {})
        # wrong parameter type
        with self.assertRaises(RuntimeError):
            st.add_parameter('test_p', {'type': 'wrong'})

    def test_add_parameter_int(self):
        st = Study(name='test', app=self.get_app())
        param = st.add_parameter('test_p', param_int)
        self.assertEqual(param.to_dict, param_int)

    def test_add_parameter_float(self):
        st = Study(name='test', app=self.get_app())
        param = st.add_parameter('test_p', param_float)
        self.assertEqual(param.to_dict, param_float)

    def test_obsname(self):
        obsname = 'obs_test'
        st = Study(name='test', app=self.get_app())
        obs = ObsName(name=obsname, study=st)
        self.assertEqual(obs.name, obsname)
        self.assertEqual(obs.study, st)

    def test_get_scenario_fail_no_scenario(self):
        with self.assertRaises(LookupError):
            self.get_app().get_scenario(
                study_name, scenario_misfit_name + 'fail')

    def test_scenario(self):
        scenario = self.get_app().get_scenario(
            study_name, scenario_misfit_name)
        self.assertEqual(scenario.name, scenario_misfit_name)

    def test_scenario_dict(self):
        scenario = self.get_app().get_scenario(
            study_name, scenario_misfit_name)
        self.assertEqual(
            scenario.to_dict,
            {'study': study_name,
             'name': scenario_misfit_name,
             'runtype': RunType.MISFIT.name,
             'num_runs': 0})

    def check_run(self, runObj, data):
        scenario = self.get_app().get_scenario(
            study_name, scenario_misfit_name)
        run = runObj(scenario, data[0])
        self.assertEqual(run.values_to_dict, data[0])

        # these should fail because run is in wrong state
        for state in [LookupState.NEW, LookupState.COMPLETED]:
            run.state = state
            with self.assertRaises(RuntimeError):
                run.set_value(data[1])
        # set state to ACTIVE
        run.state = LookupState.ACTIVE
        run.set_value({'value': data[1]})
        self.assertEqual(run.state, LookupState.COMPLETED)
        self.assertEqual(run.get_value(), {'value': data[1]})
        self.assertEqual(
            run.to_dict,
            {'id': run.id,
             'state': LookupState.COMPLETED.name,
             'value': data[1]})
        # we can also force setting a value
        run.set_value({'value': data[1]}, force=True)

    def test_run_misfit(self):
        self.check_run(RunMisfit, run_misfit)

    def test_run_path(self):
        self.check_run(RunPath, run_path)


class ObjFunRoutes(ObjFunBase):

    def test_get_auth_token(self):
        response = self.app.get('/api/token', headers=headers)
        self.assertEqual(response.status_code, 200)

    def test_auth_with_token(self):
        response = self.app.get('/api/token', headers=headers)
        token = response.get_json()['token']

        h = {}
        h['Authorization'] = 'Basic ' + base64.b64encode(
            token.encode('utf-8') + b': ').decode('utf-8')
        h['Content-Type'] = 'application/json'
        h['Accept'] = 'application/json'

        response = self.app.get('/api/token', headers=h)
        self.assertEqual(response.status_code, 200)

    def test_get_all_studies(self):
        response = self.app.get('/api/studies', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json, {'data': [{'id': 1,
                                      'name': study_name,
                                      'app': app_name,
                                      'num_scenarios': 2}]})

    def test_create_study_fail(self):
        response = self.app.post(
            '/api/create_study', json={}, headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_create_study_fail_parameter(self):
        params = dict(test_parameters)
        params['paramC'] = {'type': 'wrong'}
        response = self.app.post(
            '/api/create_study',
            json={'name': 'some_study', 'parameters': params},
            headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_create_study(self):
        response = self.app.post(
            '/api/create_study',
            json={'name': 'some_study', 'parameters': test_parameters},
            headers=headers)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json,
            {'id': 2,
             'name': 'some_study',
             'app': app_name,
             'num_scenarios': 0})

    def test_get_study_fail(self):
        response = self.app.get('/api/studies/' + 'no_study', headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_get_study(self):
        response = self.app.get(f'/api/studies/{study_name}', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json, {'id': 1,
                            'name': study_name,
                            'app': app_name,
                            'num_scenarios': 2})

    def test_get_study_params_fail_no_study(self):
        response = self.app.get(
            f'/api/studies/wrong_study/parameters', headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_get_study_params(self):
        response = self.app.get(
            f'/api/studies/{study_name}/parameters', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, test_parameters)

    def test_create_scenario_fail_no_study(self):
        response = self.app.post(
            f'/api/studies/wrong_study/create_scenario',
            json={'name': 'test', 'runtype': 'MISFIT'}, headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_create_scenario_fail_wrong_json(self):
        response = self.app.post(
            f'/api/studies/{study_name}/create_scenario',
            json={}, headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_create_scenario_fail_wrong_runtype(self):
        response = self.app.post(
            f'/api/studies/{study_name}/create_scenario',
            json={'name': 'test', 'runtype': 'wrong'}, headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_create_scenario_exists(self):
        response = self.app.post(
            f'/api/studies/{study_name}/create_scenario',
            json={'name': scenario_misfit_name, 'runtype': 'MISFIT'},
            headers=headers)
        self.assertEqual(response.status_code, 409)

    def test_create_scenario(self):
        response = self.app.post(
            f'/api/studies/{study_name}/create_scenario',
            json={'name': 'new scenario', 'runtype': 'MISFIT'},
            headers=headers)
        self.assertEqual(response.status_code, 201)

    def test_get_observation_names_fail_no_study(self):
        response = self.app.get(
            '/api/studies/wrong_study/observation_names',
            headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_get_observation_names(self):
        obsname = 'obsA'
        st = Study(name='test', app=self.get_app())
        ObsName(name=obsname, study=st)
        db.session.commit()
        response = self.app.get(
            '/api/studies/test/observation_names',
            headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'obsnames': [obsname]})

    def test_put_observation_names_fail_wrong_json(self):
        response = self.app.put(
            f'/api/studies/{study_name}/observation_names',
            json={},
            headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_put_observation_names_fail_wrong_num(self):
        obsname = 'obsA'
        st = Study(name='test', app=self.get_app())
        ObsName(name=obsname, study=st)
        db.session.commit()
        response = self.app.put(
            '/api/studies/test/observation_names',
            json={'obsnames': ['obA', 'obB']},
            headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_put_observation_names_fail_wrong_obs(self):
        obsname = 'obsA'
        st = Study(name='test', app=self.get_app())
        ObsName(name=obsname, study=st)
        db.session.commit()
        response = self.app.put(
            '/api/studies/test/observation_names',
            json={'obsnames': ['obsB']},
            headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_put_observation_names(self):
        response = self.app.put(
            f'/api/studies/{study_name}/observation_names',
            json={'obsnames': ['obsA', 'obsB']},
            headers=headers)
        self.assertEqual(response.status_code, 201)

    def test_get_all_scenarioes_fail_no_study(self):
        response = self.app.get(
            f'/api/studies/wrong_study/scenarios',
            headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_get_all_scenarioes(self):
        response = self.app.get(
            f'/api/studies/{study_name}/scenarios',
            headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json, {'data': [
                {'study': study_name,
                 'name': scenario_misfit_name,
                 'runtype': RunType.MISFIT.name,
                 'num_runs': 0},
                {'study': study_name,
                 'name': scenario_path_name,
                 'runtype': RunType.PATH.name,
                 'num_runs': 0}]})

    def test_get_all_runs_fail_no_study(self):
        response = self.app.get(
            f'/api/studies/wrong_study/scenarios/{scenario_misfit_name}/runs',
            headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_get_all_runs_fail_no_scenario(self):
        response = self.app.get(
            f'/api/studies/{study_name}/scenarios/wrong_scenario/runs',
            headers=headers)
        self.assertEqual(response.status_code, 404)


class ObjFunRoutesRuns(ObjFunBase):

    def setUp(self):
        super().setUp()
        scenario = self.get_app().get_scenario(
            study_name, scenario_misfit_name)
        run = RunMisfit(scenario, run_misfit[0])
        run.state = LookupState.COMPLETED
        run.misfit = run_misfit[1]
        db.session.commit()

    def test_get_all_runs(self):
        response = self.app.get(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/runs',
            headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json,
            {'data': [{'id': 1,
                       'state': LookupState.COMPLETED.name,
                       'value': run_misfit[1]}]})

    def test_get_run_by_params_fail_wrong_json(self):
        response = self.app.post(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'get_run', json={}, headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_get_run_by_params_fail_no_study(self):
        response = self.app.post(
            f'/api/studies/wrong_study/scenarios/{scenario_misfit_name}/'
            'get_run', json={'parameters': 'blub'}, headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_get_run_by_params_fail_wrong_params(self):
        response = self.app.post(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'get_run', json={'parameters': {'paramA': 1, 'paramB': 2}},
            headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_get_run_by_params(self):
        response = self.app.post(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'get_run', json={'parameters': run_misfit[0]},
            headers=headers)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json,
            {'id': 1,
             'state': LookupState.COMPLETED.name,
             'value': run_misfit[1]})

    def test_lookup_run_fail_wrong_json(self):
        response = self.app.post(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'lookup_run', json={}, headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_lookup_run_fail_no_study(self):
        response = self.app.post(
            f'/api/studies/wrong_study/scenarios/{scenario_misfit_name}/'
            'lookup_run', json={'parameters': 'blub'}, headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_lookup_run_new_run(self):
        response = self.app.post(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'lookup_run', json={'parameters': {'paramA': 1, 'paramB': 2}},
            headers=headers)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json,
                         {'status': 'provisional'})

    def test_lookup_run(self):
        response = self.app.post(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'lookup_run', json={'parameters': run_misfit[0]},
            headers=headers)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json,
            {'id': 1,
             'state': LookupState.COMPLETED.name,
             'value': run_misfit[1]})

    def test_get_run_with_state_fail_wrong_json(self):
        response = self.app.post(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/with_state', json={}, headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_get_run_with_state_fail_wrong_state(self):
        response = self.app.post(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/with_state', json={'state': 'wrong'}, headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_get_run_with_state_fail_wrong_new_state(self):
        response = self.app.post(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/with_state', json={'state': 'NEW', 'new_state': 'wrong'},
            headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_get_run_with_state_fail_no_study(self):
        response = self.app.post(
            f'/api/studies/wrong_study/scenarios/{scenario_misfit_name}/'
            'runs/with_state', json={'state': 'NEW'}, headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_get_run_with_state_fail_no_such_state(self):
        response = self.app.post(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/with_state', json={'state': 'NEW'}, headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_get_run_with_state(self):
        response = self.app.post(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/with_state', json={'state': 'COMPLETED'}, headers=headers)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json,
                         {'id': 1,
                          'state': LookupState.COMPLETED.name,
                          'value': run_misfit[1],
                          'values': run_misfit[0]})

    def test_get_run_by_id_fail_wrong_id(self):
        response = self.app.get(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/10', headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_get_run_by_id(self):
        response = self.app.get(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/1', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json,
                         {'id': 1,
                          'state': LookupState.COMPLETED.name,
                          'value': run_misfit[1]})

    def test_run_state_fail_wrong_id(self):
        response = self.app.get(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/10/state', headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_get_run_state(self):
        response = self.app.get(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/1/state', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'state': LookupState.COMPLETED.name})

    def test_put_run_state_fail_wrong_json(self):
        response = self.app.put(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/1/state', json={}, headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_put_run_state_fail_wrong_state(self):
        response = self.app.put(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/1/state', json={'state': 'wrong'}, headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_put_run_state(self):
        response = self.app.put(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/1/state', json={'state': 'NEW'}, headers=headers)
        self.assertEqual(response.status_code, 201)

    def test_run_value_fail_wrong_id(self):
        response = self.app.get(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/10/value', headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_get_run_value(self):
        response = self.app.get(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/1/value', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json,
                         {'value': run_misfit[1]})

    def test_put_run_value_fail_wrong_json1(self):
        response = self.app.put(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/1/value', headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_put_run_value_fail_wrong_state(self):
        response = self.app.put(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/1/value', json={'value': 10}, headers=headers)
        self.assertEqual(response.status_code, 403)

    def test_put_run_value_fail_wrong_json2(self):
        scenario = self.get_app().get_scenario(
            study_name, scenario_misfit_name)
        run = RunMisfit(scenario, {'paramA': 0, 'paramB': 20})
        run.state = LookupState.RUN
        db.session.commit()
        response = self.app.put(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/2/value', json={'wrong': 10}, headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_put_run_value(self):
        scenario = self.get_app().get_scenario(
            study_name, scenario_misfit_name)
        run = RunMisfit(scenario, {'paramA': 0, 'paramB': 20})
        run.state = LookupState.RUN
        db.session.commit()
        response = self.app.put(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/2/value', json={'value': 10}, headers=headers)
        self.assertEqual(response.status_code, 201)

    def test_put_run_value_force(self):
        response = self.app.put(
            f'/api/studies/{study_name}/scenarios/{scenario_misfit_name}/'
            'runs/1/value', json={'value': 10, 'force': True},
            headers=headers)
        self.assertEqual(response.status_code, 201)
