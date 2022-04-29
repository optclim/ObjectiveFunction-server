from .application import db, app
from itsdangerous import JSONWebSignatureSerializer as Serializer, BadSignature
from passlib.apps import custom_app_context as pwd_context


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

    __table_args__ = (
        db.UniqueConstraint('name', 'app_id', name='_unique_params'), )

    @property
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'app': self.app.name}


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
