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
            check_json({}, required_keys=['not', 'here'])


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
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()

    def get_app(self):
        app = App.query.filter_by(name=app_name).first()
        return app


class ObjFunModel(ObjFunBase):
    def setUp(self):
        super().setUp()

        # create study
        st = Study(name=study_name, app=self.get_app())
        # and some parameters
        for p in test_parameters:
            st.add_parameter(p, test_parameters[p])
        # add scenarios
        Scenario(name=scenario_misfit_name, runtype=RunType.MISFIT, study=st)
        Scenario(name=scenario_path_name, runtype=RunType.PATH, study=st)
        db.session.commit()

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
