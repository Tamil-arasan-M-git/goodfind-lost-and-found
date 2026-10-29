"""Manual database smoke check; not part of the automated test suite."""

if __name__ == "__main__":
    from auth import create_user

    try:
        user = create_user(
            "GoodFind Test User",
            "test@goodfind.com",
            "TestPassword123!"
        )
        print("User created successfully!")
        print(user)
    except Exception as error:
        print("User creation failed:")
        print(error)
