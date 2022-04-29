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
    name = db.Column(db.String, unique=True)
    app_id = db.Column(db.Integer, db.ForeignKey('apps.id'))

    app = db.relationship("App", back_populates="studies")
