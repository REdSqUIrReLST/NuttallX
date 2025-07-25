import os

def main():
    print("=== NUTtall X Launcher ===")
    print("1. Run Console Application")
    print("2. Run Web Application (Flask)")
    choice = input("Choose an option (1 or 2): ").strip()

    if choice == '1':
        os.system("python3 main.py")
    elif choice == '2':
        print("Launching Flask web app on port 3000...")
        os.environ["FLASK_APP"] = "app.py"
        os.environ["FLASK_RUN_PORT"] = "3000"
        os.system("flask run --host=0.0.0.0")
    else:
        print("Invalid choice. Exiting.")

if __name__ == "__main__":
    main()
