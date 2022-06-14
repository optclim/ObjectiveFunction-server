from .application import db
from .models import App
import argparse
import sys


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--app',
                        help="the ObjectiveFunction application")
    parser.add_argument('-p', '--password',
                        help="the password of the application")
    parser.add_argument('--init-db', action='store_true',
                        default=False, help="initialise database")
    parser.add_argument('--delete-db', action='store_true',
                        default=False, help="delete database")

    args = parser.parse_args()

    if args.init_db:
        db.create_all()
    elif args.delete_db:
        db.drop_all()
    elif args.app is not None:
        if args.password is None:
            parser.error('need to set password')
            sys.exit(1)
        a = App(name=args.app)
        a.hash_password(args.password)
        db.session.add(a)
        db.session.commit()


if __name__ == '__main__':
    main()
