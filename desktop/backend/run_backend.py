import os
import multiprocessing

if __name__ == '__main__':
    multiprocessing.freeze_support()
    import uvicorn
    from app.main import app
    uvicorn.run(app, host='127.0.0.1', port=int(os.environ.get('COURSE_PORT', '8765')),
                loop='asyncio', log_level='warning', access_log=False)
