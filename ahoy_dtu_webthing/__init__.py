from ahoy_dtu_webthing.app import App, ArgumentSpec
from ahoy_dtu_webthing.dtu_webthing import run_server

def main():
    App.run(run_function=lambda args, desc: run_server(description=desc, port=args['port'], base_uri=args['base_uri']),
            packagename="ahoy_dtu_webthing",
            arg_specs=[ArgumentSpec("base_uri", str, "the base uri", True)])

if __name__ == '__main__':
    main()
