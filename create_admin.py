from getpass import getpass

from app import app, db, User

if __name__ == "__main__":
    with app.app_context():
        email = input("Founder email: ").strip().lower()
        name = input("Founder name: ").strip()
        password = getpass("Password: ")

        existing = User.query.filter_by(email=email).first()
        if existing:
            print("User with that email already exists.")
        else:
            user = User(name=name, email=email, role="founder", active=True)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            print("Founder user created.")
