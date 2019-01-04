# boac

bCourses offers analytic choices.

## Installation

* Install Python 3
* Create your virtual environment (venv)
* Install dependencies

```
pip3 install -r requirements.txt [--upgrade]
pip3 install pandas==0.23.3
```

### Front-end dependencies

```
npm install
npm install -g bower
bower install
```

### Create Postgres user and databases

```
createuser boac --no-createdb --no-superuser --no-createrole --pwprompt
createdb boac --owner=boac
createdb boac_test --owner=boac
createdb boac_loch_test --owner=boac

# Load schema
export FLASK_APP=run.py
flask initdb
```

### Create local configurations

If you plan to use any resources outside localhost, put your configurations in a separately encrypted area:

```
mkdir /Volumes/XYZ/boac_config
export BOAC_LOCAL_CONFIGS=/Volumes/XYZ/boac_config
```

## Run tests, lint the code

We use [Tox](https://tox.readthedocs.io) for continuous integration. Under the hood, you'll find [PyTest](https://docs.pytest.org), [Flake8](http://flake8.pycqa.org), [ESLint](https://eslint.org/) and [Stylelint](https://stylelint.io). Please install NPM dependencies (see above) before running tests.
```
# Run all tests and linters
tox

# Pytest only
tox -e test

# Linters, à la carte
tox -e lint-css
tox -e lint-js
tox -e lint-py
tox -e lint-vue

# Auto-fix linting errors in Vue code
tox -e lint-vue-fix

# Run specific test(s)
tox -e test -- tests/test_models/test_authorized_user.py
tox -e test -- tests/test_externals/

# Lint specific file(s)
tox -e lint-js -- boac/static/js/controllers/cohortController.js
tox -e lint-py -- scripts/cohort_fixtures.py
```
