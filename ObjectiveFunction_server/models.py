from .application import db, app
from itsdangerous import JSONWebSignatureSerializer as Serializer, BadSignature
from passlib.apps import custom_app_context as pwd_context
import logging
import pandas

from .common import RunType, LookupState


class App(db.Model):
    __tablename__ = 'apps'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), index=True)
    password_hash = db.Column(db.String(128))

    def __repr__(self):
        return '<App {}>'.format(self.name)

    def hash_password(self, password):
        self.password_hash = pwd_context.hash(password)

    def verify_password(self, password):
        return pwd_context.verify(password, self.password_hash)

    def generate_auth_token(self):
        s = Serializer(app.config['SECRET_KEY'])
        return s.dumps({'id': self.id})

    @staticmethod
    def verify_auth_token(token):
        s = Serializer(app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except BadSignature:
            return None  # invalid token
        objfun_app = App.query.get(data['id'])
        return objfun_app

    def get_study(self, study):
        study = Study.query.filter_by(name=study, app=self).one_or_none()
        if not study:
            raise LookupError(f'no study {study} for app {self.name}')
        return study

    def get_scenario(self, study, scenario):
        study = self.get_study(study)
        scenario = Scenario.query.filter_by(
            name=scenario, study=study).one_or_none()
        if not scenario:
            raise LookupError(f'no scenario {scenario} for study {study}'
                              f' for app {self.name}')
        return scenario

    def get_run(self, study, scenario, runid):
        scenario = self.get_scenario(study, scenario)
        run = scenario.get_run_by_id(runid)
        if run is None:
            raise LookupError(
                f'no run with ID {runid} for scenario {scenario} '
                f'of study {study}')
        return run

    studies = db.relationship("Study", back_populates="app")


class Study(db.Model):
    __tablename__ = 'studies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    app_id = db.Column(db.Integer, db.ForeignKey('apps.id'))

    app = db.relationship("App", back_populates="studies")
    obsnames = db.relationship("ObsName", order_by="ObsName.name",
                               back_populates="study")
    parameters = db.relationship("Parameter", order_by="Parameter.name",
                                 back_populates="study")
    scenarios = db.relationship("Scenario", back_populates="study")

    __table_args__ = (
        db.UniqueConstraint('name', 'app_id', name='_unique_params'), )

    @property
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'app': self.app.name,
            'num_scenarios': len(self.scenarios)}

    def add_parameter(self, name, parameter):
        if 'type' not in parameter:
            raise RuntimeError('parameter does not contain type')
        if parameter['type'] == 'int':
            param = ParameterInt(
                study=self, name=name,
                minv=parameter['minv'], maxv=parameter['maxv'])
        elif parameter['type'] == 'float':
            param = ParameterFloat(
                study=self, name=name,
                minv=parameter['minv'], maxv=parameter['maxv'],
                resolution=parameter['resolution'])
        else:
            raise RuntimeError(
                f'unknown parameter type {parameter["type"]}')
        return param


class ObsName(db.Model):
    __tablename__ = 'obsnames'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    study_id = db.Column(db.Integer, db.ForeignKey('studies.id'))

    study = db.relationship("Study", back_populates="obsnames")

    __table_args__ = (
        db.UniqueConstraint('name', 'study_id', name='_unique_params'), )


class Parameter(db.Model):
    __tablename__ = 'parameters'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    study_id = db.Column(db.Integer, db.ForeignKey('studies.id'))
    type = db.Column(db.String)

    study = db.relationship("Study", back_populates="parameters")

    __table_args__ = (
        db.UniqueConstraint('name', 'study_id', name='_unique_params'), )

    __mapper_args__ = {
        'polymorphic_identity': 'parameter',
        'polymorphic_on': type}


class ParameterInt(Parameter):
    __tablename__ = 'parameters_int'

    id = db.Column(db.Integer, db.ForeignKey('parameters.id'),
                   primary_key=True)
    minv = db.Column(db.Integer)
    maxv = db.Column(db.Integer)

    __mapper_args__ = {
        'polymorphic_identity': 'parameterint'}

    @property
    def to_dict(self):
        return {
            'type': 'int',
            'minv': self.minv,
            'maxv': self.maxv}


class ParameterFloat(Parameter):
    __tablename__ = 'parameters_float'

    id = db.Column(db.Integer, db.ForeignKey('parameters.id'),
                   primary_key=True)
    minv = db.Column(db.Float)
    maxv = db.Column(db.Float)
    resolution = db.Column(db.Float)

    __mapper_args__ = {
        'polymorphic_identity': 'parameterfloat'}

    @property
    def to_dict(self):
        return {
            'type': 'float',
            'minv': self.minv,
            'maxv': self.maxv,
            'resolution': self.resolution}


class Scenario(db.Model):
    __tablename__ = 'scenarios'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    runtype = db.Column(db.Enum(RunType))
    study_id = db.Column(db.Integer, db.ForeignKey('studies.id'))

    study = db.relationship("Study", back_populates="scenarios")
    runs = db.relationship("Run", back_populates="scenario")

    __table_args__ = (db.UniqueConstraint('name', 'study_id',
                                          name='_unique_scenario'), )

    @property
    def _Run(self):
        if self.runtype == RunType.MISFIT:
            return RunMisfit
        elif self.runtype == RunType.PATH:
            return RunPath
        else:
            raise ValueError(f'unknown runtype {self.runtype}')

    @property
    def to_dict(self):
        return {'study': self.study.name,
                'name': self.name,
                'runtype': self.runtype.name,
                'num_runs': len(self.runs)}

    def get_run_by_id(self, runid):
        """get a run with a particular id

        :param runid: the run ID
        """
        return self._Run.query.filter_by(
            scenario=self, id=runid).one_or_none()

    def get_run(self, parameters):
        """get a run for a particular parameter set

        :param parmeters: dictionary containing parameter values
        """

        dbParams = {}
        dbParams['runid'] = []
        for p in self.study.parameters:
            dbParams[p.name] = []
        for run in self.runs:
            dbParams['runid'].append(run.id)
            for p in run.values:
                dbParams[p.parameter.name].append(p.value)

        # turn into pandas dataframe to query
        dbParams = pandas.DataFrame(dbParams)
        # construct query
        query = []
        for p in self.study.parameters:
            v = parameters[p.name]
            query.append('({}=={})'.format(p.name, v))
        query = ' & '.join(query)
        runid = dbParams.query(query)
        if len(runid) == 0:
            raise LookupError("no entry for parameter set found")
        runid = int(runid.runid.iloc[0])
        return self.get_run_by_id(runid)

    def lookup_run(self, parameters):
        """look up run with a particular parameter set

        create a new run if no parameter set is found

        :param parmeters: dictionary containing parameter values
        """

        run = None
        try:
            run = self.get_run(parameters)
        except LookupError:
            pass

        if run is None:
            # check if we already have a provisional entry
            run = self._Run.query.filter_by(
                scenario=self, state=LookupState.PROVISIONAL).first()
            if run is not None:
                # we already have a provisional value
                # delete the previous one and wait
                logging.info('remove provisional parameter set')
                db.session.delete(run)
                db.session.commit()
                return 'waiting'

            logging.info('new provisional parameter set')
            run = self._Run(self, parameters)
            run.state = LookupState.PROVISIONAL
            db.session.commit()
            return 'provisional'
        else:
            if run.state == LookupState.PROVISIONAL:
                logging.info('provisional parameter set changed to new')
                run.state = LookupState.NEW
                db.session.commit()
                return 'new'
            elif run.state == LookupState.COMPLETED:
                logging.debug('hit completed parameter set')
            else:
                logging.debug('hit new/active parameter set')
        return run

    def get_run_with_state(self, state, new_state=None):
        """get a set of parameters in a particular state

        :param state: find run in state
        :param new_state: when not None set the state of the run to new_state

        Get a set of parameters for a run in a particular state. Optionally
        the run transitions to new_state.
        """
        query = self._Run.query.filter_by(
            scenario=self, state=state)
        if new_state is not None:
            query = query.with_for_update()
        run = query.first()
        if run is None:
            raise LookupError(f'no parameter set in state {state.name}')

        if new_state is not None:
            run.state = new_state
            db.session.commit()

        return run


class Run(db.Model):
    __tablename__ = 'runs'

    id = db.Column(db.Integer, primary_key=True)
    scenario_id = db.Column(db.Integer, db.ForeignKey('scenarios.id'))
    state = db.Column(db.Enum(LookupState))
    type = db.Column(db.String)

    values = db.relationship("RunParameters", back_populates="_run",
                             cascade="all, delete-orphan")
    scenario = db.relationship("Scenario", back_populates="runs")

    __mapper_args__ = {
        'polymorphic_identity': 'run',
        'polymorphic_on': type}

    def __init__(self, scenario, parameters):
        self.scenario = scenario
        for db_param in self.scenario.study.parameters:
            RunParameters(
                _run=self, parameter=db_param,
                value=parameters[db_param.name])

    @property
    def to_dict(self):
        return {'id': self.id,
                'state': self.state.name}

    @property
    def values_to_dict(self):
        values = {}
        for v in self.values:
            values[v.parameter.name] = v.value
        return values

    def _set_value(self, value):
        raise NotImplementedError

    def set_value(self, value, force=False):
        if (self.state.value > LookupState.CONFIGURED.value
            and self.state != LookupState.COMPLETED) or force:  # noqa W503
            self._set_value(value)
            self.state = LookupState.COMPLETED
            db.session.commit()
        else:
            raise RuntimeError(
                f'parameter set is in wrong state {self.state}')

    def get_value(self):
        raise NotImplementedError


class RunMisfit(Run):
    __tablename__ = 'runs_misfit'

    id = db.Column(db.Integer, db.ForeignKey('runs.id'), primary_key=True)
    misfit = db.Column(db.Float)

    __mapper_args__ = {
        'polymorphic_identity': 'residual'}

    @property
    def to_dict(self):
        d = super().to_dict
        d['value'] = self.misfit
        return d

    def _set_value(self, value):
        self.misfit = value['value']

    def get_value(self):
        return {'value': self.misfit}


class RunPath(Run):
    __tablename__ = 'runs_path'

    id = db.Column(db.Integer, db.ForeignKey('runs.id'), primary_key=True)
    path = db.Column(db.String)

    __mapper_args__ = {
        'polymorphic_identity': 'path'}

    @property
    def to_dict(self):
        d = super().to_dict
        d['value'] = self.path
        return d

    def _set_value(self, value):
        self.path = value['value']

    def get_value(self):
        return {'value': self.path}


class RunParameters(db.Model):
    __tablename__ = 'run_parameters'

    id = db.Column(db.Integer, primary_key=True)
    lid = db.Column(db.Integer, db.ForeignKey('runs.id'))
    pid = db.Column(db.Integer, db.ForeignKey('parameters.id'))
    value = db.Column(db.Integer)

    _run = db.relationship("Run", back_populates="values")
    parameter = db.relationship("Parameter")
