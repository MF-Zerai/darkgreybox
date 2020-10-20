import numpy as np
import pandas as pd
import copy
from timeit import default_timer as timer
from joblib import Parallel, delayed


def train_models(models, X_train, y_train, error_metric,
                 splits=None, method='nelder', n_jobs=-1, verbose=10):
    """
    Trains the `models` for the given `X_train` and `y_train` training data
    for `splits` using `method`. 

    Params:
        models: list of `model.DarkGreyModel` objects
            list of models to be trained
        X_train: `pandas.DataFrame`
            A pandas DataFrame of the training input data X
        y_train: `pandas.Series`
            A pandas Series of the training input data y
        error_metric: function
            An error metric function that confirms to the `sklearn.metrics` interface
        splits: list
            A list of training data indices specifying sub-sections of `X_train` and `y_train` 
            for the models to be trained on
        method : str
            Name of the fitting method to use. Valid values are described in:
            `lmfit.minimize`
        n_jobs: int
            The number of parallel jobs to be run as described by `joblib.Parallel`
        verbose: int
            The degree of verbosity as described by `joblib.Parallel`

    Returns:
        `pandas.DataFrame` with a record for each model's result for each split

    Example:
    ~~~~
    
    from sklearn.metrics import mean_squared_error
    from sklearn.model_selection import KFold

    from darkgreybox.model import TiTe
    from darkgreybox.fit import train_models


    prefit_df = train_models(models=[TiTe(train_params, rec_duration=1)],
                             X_train=X_train, 
                             y_train=y_train, 
                             splits=KFold(n_splits=int(len(X_train) / 24), shuffle=False).split(X_train), 
                             error_metric=mean_squared_error,
                             method='nelder', 
                             n_jobs=-1, 
                             verbose=10)
    ~~~~
    """

    if n_jobs != 1:
        with Parallel(n_jobs=n_jobs, verbose=verbose) as p:
            df = pd.concat(p(delayed(train_model)(model, X_train.iloc[idx], y_train.iloc[idx], error_metric, method)
                             for _, idx in splits or [(None, range(len(X_train)))] for model in models), ignore_index=True)

    else:
        df = pd.concat([train_model(model, X_train.iloc[idx], y_train.iloc[idx], error_metric, method)
                         for _, idx in splits or [(None, range(len(X_train)))] for model in models], ignore_index=True)

    return df


def train_model(base_model, X_train, y_train, error_metric, method='nelder'):
    """
    Trains a copy of `basemodel` for the given `X_train` and `y_train` training data
    using `method`. 

    Params:
        base_model: `model.DarkGreyModel`
            model to be trained (a copy will be made)
        X_train: `pandas.DataFrame`
            A pandas DataFrame of the training input data X
        y_train: `pandas.Series`
            A pandas Series of the training input data y
        error_metric: function
            An error metric function that confirms to the `sklearn.metrics` interface
        method : str
            Name of the fitting method to use. Valid values are described in:
            `lmfit.minimize`

    Returns:
        `pandas.DataFrame` with a single record for the fit model's result 
    """

    start = timer()
    model = copy.deepcopy(base_model)
    
    try:
        model = model.fit(X=X_train.to_dict(orient='list'),
                          y=y_train.values,
                          method=method,
                          ic_params=get_ic_params(model, X_train))
    except ValueError:
        end = timer()
        return pd.DataFrame({'start_date': [X_train.index[0]],
                             'end_date': [X_train.index[-1]],
                             'model': [np.NaN],
                             'model_result': [np.NaN],
                             'time': [end - start],
                             'method': [method],
                             'error': [np.NaN]})

    model_result = model.predict(X_train)
    end = timer()

    return pd.DataFrame({'start_date': [X_train.index[0]],
                         'end_date': [X_train.index[-1]],
                         'model': [model],
                         'model_result': [model_result],
                         'time': [end - start],
                         'method': [method],
                         'error': [error_metric(y_train.values, model_result.Z)]})


def reduce_results_df(df, decimals=6):
    return (df.replace([-np.inf, np.inf], np.nan)
              .dropna()
              .round({'error': decimals})
              .sort_values('time')
              .drop_duplicates(subset=['error'], keep='first')
              .sort_values('error')
              .reset_index(drop=True))


def get_ic_params(model, X_train):
    """
    Returns the initial condition parameters of a model from the training data

    Params:
        model: `model.DarkGreyModel`
            model to get initial condition parameters from
        X_train: `pandas.DataFrame`
            A pandas DataFrame of the training input data X    

    Returns:
        A dictionary containing the initial conditions and their corresponding values 
        as defined by the training data

    """

    # TODO: this is horrible - make this clearer and more robust
    ic_params = {}
    for key in model.params:
        if '0' in key:
            ic_params[key] = X_train.iloc[0][key]

    return ic_params
