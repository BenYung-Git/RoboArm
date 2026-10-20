import uvicorn

from app.storage.config_store import load_app_config

if __name__ == "__main__":
    config = load_app_config()
    uvicorn.run(
        "app.main:app",
        host=config["host"],
        port=int(config["port"]),
        reload=False,
    )
