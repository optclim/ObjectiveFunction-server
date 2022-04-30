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

    studies = db.relationship("Study", back_populates="app")


class Study(db.Model):
    __tablename__ = 'studies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    app_id = db.Column(db.Integer, db.ForeignKey('apps.id'))

    app = db.relationship("App", back_populates="studies")
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
        return self._Run.query.filter_by(id=runid).one()

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
                scenario=self, state=LookupState.PROVISIONAL).one_or_none()
            if run is not None:
                # we already have a provisional value
                # delete the previous one and wait
                logging.info('remove provisional parameter set')
                db.session.delete(run)
                db.session.commit()
                return

            logging.info('new provisional parameter set')
            run = self._Run(self, parameters)
            run.state = LookupState.PROVISIONAL
            db.session.commit()
        else:
            if run.state == LookupState.PROVISIONAL:
                logging.info('provisional parameter set changed to new')
                run.state = LookupState.NEW
                db.session.commit()
            elif run.state == LookupState.COMPLETED:
                logging.debug('hit completed parameter set')
            else:
                logging.debug('hit new/active parameter set')
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


class RunMisfit(Run):
    __tablename__ = 'runs_misfit'

    id = db.Column(db.Integer, db.ForeignKey('runs.id'), primary_key=True)
    misfit = db.Column(db.Float)

    __mapper_args__ = {
        'polymorphic_identity': 'residual'}

    @property
    def to_dict(self):
        d = super().to_dict
        d['misfit'] = self.misfit
        return d


class RunPath(Run):
    __tablename__ = 'runs_path'

    id = db.Column(db.Integer, db.ForeignKey('runs.id'), primary_key=True)
    path = db.Column(db.String)

    __mapper_args__ = {
        'polymorphic_identity': 'path'}

    @property
    def to_dict(self):
        d = super().to_dict
        d['path'] = self.path
        return d


class RunParameters(db.Model):
    __tablename__ = 'run_parameters'

    id = db.Column(db.Integer, primary_key=True)
    lid = db.Column(db.Integer, db.ForeignKey('runs.id'))
    pid = db.Column(db.Integer, db.ForeignKey('parameters.id'))
    value = db.Column(db.Integer)

    _run = db.relationship("Run", back_populates="values")
    parameter = db.relationship("Parameter")