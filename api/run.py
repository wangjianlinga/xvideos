import uvicorn
import sys

if __name__ == "__main__":
    try:
        uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)
    except KeyboardInterrupt:
        print("\nServer stopped.")
        sys.exit(0)
