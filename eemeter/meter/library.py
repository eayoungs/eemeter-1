from .base import MeterBase

from datetime import datetime
from datetime import timedelta
from eemeter.evaluation import Period
import pytz

from itertools import chain
import numpy as np

import re

class TemperatureSensitivityParameterOptimizationMeter(MeterBase):
    """Optimizes temperature senstivity parameter choices.

    Parameters
    ----------
    temperature_unit_str : str
        Unit of temperature, usually "degC" or "degF".
    model : eemeter.model.TemperatureSensitivityModel
        Model of energy usage for which to optimize parameter choices.
    """

    def __init__(self, temperature_unit_str, model, **kwargs):
        super(TemperatureSensitivityParameterOptimizationMeter,
                self).__init__(**kwargs)
        self.temperature_unit_str = temperature_unit_str
        self.model = model

    def evaluate_mapped_inputs(self, consumption_data, weather_source,
            fuel_unit_str, **kwargs):
        """Run optimization of temperature sensitivity parameters given a
        observed consumption data, and observed temperature data.

        Parameters
        ----------
        consumption_data : eemeter.consumption.ConsumptionHistory
            Consumption history to use as basis of model.
        weather_source : eemeter.weather.WeatherSourceBase
            Weather data source containing data covering at least the duration
            of the consumption data.
        fuel_unit_str : str
            Unit of fuel, usually "kWh" or "therms".

        Returns
        -------
        out : dict
            - "temp_sensitivity_params": an array of optimal parameters
            - "average_daily_usages": an array of actual average daily usages
            - "estimated_average_daily_usages": an array of estimated usages
              as given by the model.
            - "n_days": an array of the number of days in each consumption
              period (weights)
        """
        average_daily_usages, n_days = \
                consumption_data.average_daily_consumptions()
        periods = consumption_data.periods()
        observed_daily_temps = weather_source.daily_temperatures(periods,
                self.temperature_unit_str)

        params = self.model.parameter_optimization(average_daily_usages,
                observed_daily_temps, n_days)

        estimated_daily_usages = self.model.compute_usage_estimates(params,
                observed_daily_temps) / n_days

        return {"temp_sensitivity_params": params,
                "average_daily_usages": average_daily_usages,
                "estimated_average_daily_usages": estimated_daily_usages,
                "n_days": n_days}

class AnnualizedUsageMeter(MeterBase):
    """Weather normalizes modeled usage for an annualized estimate of
    consumption.

    Parameters
    ----------
    temperature_unit_str : str
        Unit of temperature, usually "degC" or "degF".
    model : eemeter.model.TemperatureSensitivityModel
        Model of energy usage
    """

    def __init__(self, temperature_unit_str, model, **kwargs):
        super(AnnualizedUsageMeter,self).__init__(**kwargs)
        self.temperature_unit_str = temperature_unit_str
        self.model = model

    def evaluate_mapped_inputs(self, temp_sensitivity_params,
            weather_normal_source, **kwargs):
        """Evaluates the annualized usage metric given a particular set of
        model parameters and a weather normal source.

        Parameters
        ----------
        temp_sensitivity_params : object
            Parameters in a format recognized by the model
            `compute_usage_estimates` method.
        weather_normal_source : eemeter.weather.WeatherBase and eemeter.weather.WeatherNormalMixin
            Weather normal data source. Should be from a location (station) as
            geographically and climatically similar to project as possible.

        Returns
        -------
        out : dict
            Dictionary with annualized usage given temperature sensitivity
            parameters and weather normals keyed by the string
            "annualized_usage"
        """
        daily_temps = weather_normal_source.annual_daily_temperatures(
                self.temperature_unit_str)
        usage_estimates = self.model.compute_usage_estimates(
                temp_sensitivity_params, daily_temps)

        annualized_usage = np.nansum(usage_estimates)
        return {"annualized_usage": annualized_usage}

class GrossSavingsMeter(MeterBase):
    """Calculates savings due to an efficiency retrofit of ECM for a particular
    fuel type using a conterfactual usage estimate and actual usage.

    Parameters
    ----------
    model : eemeter.model.TemperatureSensitivityModel
        Model of energy usage
    fuel_unit_str : str
        Unit of fuel, usually "kWh" or "therms".
    temperature_unit_str : str
        Unit of temperature, usually "degC" or "degF".
    """

    def __init__(self, model, fuel_unit_str, temperature_unit_str,
            **kwargs):
        super(GrossSavingsMeter, self).__init__(**kwargs)
        self.model = model
        self.fuel_unit_str = fuel_unit_str
        self.temperature_unit_str = temperature_unit_str

    def evaluate_mapped_inputs(self, temp_sensitivity_params_pre,
            consumption_data_post, weather_source, **kwargs):
        """Evaluates the gross savings metric.

        Parameters
        ----------
        temp_sensitivity_params_pre : object
            Parameters in a format recognized by the model
            `compute_usage_estimates` method.
        consumption_data_post : eemeter.consumption.ConsumptionData
            Consumption periods over which gross savings estimate will be
            calculated.
        weather_source : eemeter.weather.WeatherSourceBase
            Weather data source containing data covering at least the duration
            of the consumption data.

        Returns
        -------
        out : dict
            Gross savings keyed by the string "gross_savings"

        """
        consumption_periods = consumptions_data_post.periods()
        usages_post = consumptions_data_post.to(self.fuel_unit_str)
        observed_daily_temps = weather_source.daily_temperatures(
                consumption_periods, self.temperature_unit_str)
        usage_estimates_pre = self.model.compute_usage_estimates(
                temp_sensitivity_params_pre, observed_daily_temps)
        return {"gross_savings": np.nansum(usage_estimates_pre - usages_post)}

class AnnualizedGrossSavingsMeter(MeterBase):
    """Annualized gross savings accumulated since the completion of a retrofit
    calculated by multiplying an annualized savings estimate by the number
    of years since retrofit completion.

    Parameters
    ----------
    model : eemeter.model.TemperatureSensitivityModel
        Model of energy usage
    fuel_type : str
        Type of fuel, usually "electricity" or "natural_gas".
    temperature_unit_str : str
        Unit of temperature, usually "degC" or "degF".
    """

    def __init__(self, model, fuel_type, temperature_unit_str, **kwargs):
        super(AnnualizedGrossSavingsMeter,self).__init__(**kwargs)
        self.model = model
        self.fuel_type = fuel_type
        self.temperature_unit_str = temperature_unit_str

    def evaluate_mapped_inputs(self, temp_sensitivity_params_pre,
            temp_sensitivity_params_post, consumption_data_post,
            weather_normal_source, **kwargs):
        """Evaluates the annualized gross savings metric.

        Parameters
        ----------
        temp_sensitivity_params_pre : object
            Parameters for pre-retrofit period in a format recognized by the
            model `compute_usage_estimates` method.
        temp_sensitivity_params_post : object
            Parameters for post-retrofit period in a format recognized by the
            model `compute_usage_estimates` method.
        consumption_data_post : eemeter.consumption.ConsumptionData
            Consumption periods over which annualized gross savings estimate will be
            calculated. (Note: only used for finding appropriate number of days
            multiplier).
        weather_normal_source : eemeter.weather.WeatherBase and eemeter.weather.WeatherNormalMixin
            Weather normal data source. Should be from a location (station) as
            geographically and climatically similar to project as possible.

        Returns
        -------
        out : dict
            Annualized gross savings keyed by the string "annualized_gross_savings".
        """

        meter = AnnualizedUsageMeter(self.temperature_unit_str,self.model)
        annualized_usage_pre = meter.evaluate(
                temp_sensitivity_params=temp_sensitivity_params_pre,
                weather_normal_source=weather_normal_source)["annualized_usage"]
        annualized_usage_post = meter.evaluate(
                temp_sensitivity_params=temp_sensitivity_params_post,
                weather_normal_source=weather_normal_source)["annualized_usage"]
        annualized_usage_savings = annualized_usage_pre - annualized_usage_post
        n_years = consumption_data_post.total_days()/365.
        annualized_gross_savings = n_years * annualized_usage_savings
        return {"annualized_gross_savings": annualized_gross_savings}

class FuelTypePresenceMeter(MeterBase):
    """Checks for fuel type presence in a given project.

    Parameters
    ----------
    fuel_types : list of str
        Names of fuel types to be evaluated for presence.
    """

    def __init__(self, fuel_types, **kwargs):
        super(FuelTypePresenceMeter,self).__init__(**kwargs)
        self.fuel_types = fuel_types

    def evaluate_mapped_inputs(self, project, **kwargs):
        """Check for fuel type presence.

        Parameters
        ----------
        project : eemeter.project.Project
            Project in which to check for presence of data.

        Returns
        -------
        out : dict
            A dictionary of booleans keyed by `"[fuel_type]_presence"` (e.g.
            `fuel_types = ["electricity"]` => `{'electricity_presence': False}`
        """
        results = {"{}_presence".format(ft): False for ft in self.fuel_types}
        for consumption in project.consumptions:
            if consumption.fuel_type in self.fuel_types:
                results["{}_presence".format(consumption.fuel_type)] = True
        return results

class ForEachFuelType(MeterBase):
    """Executes a meter once for each fuel type.

    Parameters
    ----------
    fuel_types : list of str
        Fuel types to execute meter for; e.g. ["electricity","natural_gas"]
    fuel_unit_strs : list of str
        Fuel units to use during meter execution.
    meter : eemeter.meter.MeterBase
        Meter to execute once for each fuel type.
    gathered_inputs : list of str
        Key strings for fuel-type-specific inputs that should be gathered and
        cleaned. Keys in this list will be remapped from "\*_{fuel_type}" to
        "\*_current_fuel". E.g. "output_electricity" -> "output_current_fuel".
        This increases meter reusability.
    """
    def __init__(self, fuel_types, fuel_unit_strs, meter, gathered_inputs=[],
            **kwargs):
        super(ForEachFuelType,self).__init__(**kwargs)
        self.fuel_types = fuel_types
        self.fuel_unit_strs = fuel_unit_strs
        if not len(fuel_types) == len(fuel_unit_strs):
            raise ValueError("Fuel types and units lists must have matching lengths.")
        self.meter = meter
        self.gathered_inputs = gathered_inputs

    def evaluate_mapped_inputs(self, **kwargs):
        """Evaluates the meter once for each fuel type; appending
        "_{fuel_type}" to the each result of the meter.

        Returns
        -------
        out : dict
            Dictionary of outputs containing all results with appended
            fuel_type markers in keys as described above.
        """
        results = {}
        for fuel_type, fuel_unit_str in zip(self.fuel_types, self.fuel_unit_strs):
            inputs = {}
            p = re.compile("(_{}$)".format(fuel_type))
            for k,v in kwargs.items():
                stripped_k = p.sub('',k)
                if stripped_k in self.gathered_inputs:
                    subbed_key = p.sub('_current_fuel', k)
                    inputs[subbed_key] = v
                else:
                    inputs[k] = v
            inputs["fuel_type"] = fuel_type
            inputs["fuel_unit_str"] = fuel_unit_str

            result = self.meter.evaluate(**inputs)
            for k,v in result.items():
                results[ "{}_{}".format(k, fuel_type)] = v
        return results

class TimeSpanMeter(MeterBase):
    """Meters the time span (in days) of a ConsumptionData instance.
    """
    def __init__(self, **kwargs):
        super(TimeSpanMeter, self).__init__(**kwargs)

    def evaluate_mapped_inputs(self, consumption_data, **kwargs):
        """Evaluates a ConsumptionHistory instance to determine the number of
        unique days covered by consumption periods

        Parameters
        ----------
        consumption_data : eemeter.consumption.ConsumptionData
            Target of time span analysis

        Returns
        -------
        out : dict
            Contains an item with the key "time_span" containing the number of
            days covered by the consumption history.
        """
        return { "time_span": consumption_data.total_days() }

class TotalHDDMeter(MeterBase):
    """Sums the total heating degree days observed over the course of a
    ConsumptionHistory instance

    Parameters
    ----------
    base : int or float
        The heating degree day base.
    temperature_unit_str : {"degF", "degC"}
        A string denoting the temperature unit to be used.
    """
    def __init__(self,base,temperature_unit_str,**kwargs):
        super(TotalHDDMeter,self).__init__(**kwargs)
        self.base = base
        self.temperature_unit_str = temperature_unit_str

    def evaluate_mapped_inputs(self, consumption_data, weather_source,**kwargs):
        """Sums the total observed HDD over a consumption history.

        Parameters
        ----------
        consumption_data : eemeter.meter.ConsumptionData
            The consumption data over which to sum heating degree days
        weather_source : eemeter.weather.WeatherSourceBase
            A weather data source from a location as geographically and
            climatically close as possible to the target project.

        Returns
        -------
        out : dict
            Contains a single item with the key "total_hdd" containing the
            total HDDs observed during the period
        """
        consumption_periods = consumption_data.periods()
        hdd = weather_source.hdd(consumption_periods,
                self.temperature_unit_str, self.base)
        return { "total_hdd": sum(hdd) }

class TotalCDDMeter(MeterBase):
    """Sums the total cooling degree days observed over the course of a
    ConsumptionHistory instance

    Parameters
    ----------
    base : int or float
        The cooling degree day base.
    temperature_unit_str : {"degF", "degC"}
        A string denoting the temperature unit to be used.
    """
    def __init__(self, base, temperature_unit_str, **kwargs):
        super(TotalCDDMeter,self).__init__(**kwargs)
        self.base = base
        self.temperature_unit_str = temperature_unit_str

    def evaluate_mapped_inputs(self, consumption_data, weather_source,
            **kwargs):
        """Sums the total observed CDD over a consumption history.

        Parameters
        ----------
        consumption_data : eemeter.meter.ConsumptionData
            The consumption data over which to sum cooling degree days
        weather_source : eemeter.weather.WeatherSourceBase
            A weather data source from a location as geographically and
            climatically close as possible to the target project.

        Returns
        -------
        out : dict
            Contains a single item with the key "total_cdd" containing the
            total CDDs observed during the period
        """
        consumption_periods = consumption_data.periods()
        cdd = weather_source.cdd(consumption_periods,
                self.temperature_unit_str, self.base)
        return { "total_cdd": sum(cdd) }


class NormalAnnualHDD(MeterBase):
    """Sums the total heating degree days observed in a normal year.

    Parameters
    ----------
    base : int or float
        The heating degree day base.
    temperature_unit_str : {"degF", "degC"}
        A string denoting the temperature unit to be used.
    """
    def __init__(self, base, temperature_unit_str, **kwargs):
        super(NormalAnnualHDD,self).__init__(**kwargs)
        self.base = base
        self.temperature_unit_str = temperature_unit_str

    def evaluate_mapped_inputs(self, weather_normal_source, **kwargs):
        """Sums the total observed HDD in a normal year

        Parameters
        ----------
        weather_normal_source : eemeter.weather.WeatherSourceBase and eemeter.weather.WeatherNormalMixin
            A weather data source from a location as geographically and
            climatically close as possible to the target project.

        Returns
        -------
        out : dict
            Contains a single item with the key "normal_annual_hdd" containing the
            total HDDs observed during the normal year
        """
        # year of this annual period will be ignored
        annual_period = Period(datetime(2013,1,1), datetime(2014,1,1))
        hdd = weather_normal_source.hdd(annual_period,
                self.temperature_unit_str, self.base)
        return { "normal_annual_hdd": hdd }

class NormalAnnualCDD(MeterBase):
    """Sums the total cooling degree days observed in a normal year.

    Parameters
    ----------
    base : int or float
        The heating degree day base.
    temperature_unit_str : {"degF", "degC"}
        A string denoting the temperature unit to be used.
    """
    def __init__(self, base, temperature_unit_str, **kwargs):
        super(NormalAnnualCDD,self).__init__(**kwargs)
        self.base = base
        self.temperature_unit_str = temperature_unit_str

    def evaluate_mapped_inputs(self, weather_normal_source, **kwargs):
        """Sums the total observed CDD in a normal year

        Parameters
        ----------
        weather_normal_source : eemeter.weather.WeatherSourceBase and eemeter.weather.WeatherNormalMixin
            A weather data source from a location as geographically and
            climatically close as possible to the target project.

        Returns
        -------
        out : dict
            Contains a single item with the key "normal_annual_cdd" containing the
            total CDDs observed during the normal year
        """

        annual_period = Period(datetime(2013,1,1), datetime(2014,1,1))
        cdd = weather_normal_source.cdd(annual_period,
                self.temperature_unit_str, self.base)
        return { "normal_annual_cdd": cdd }

class NPeriodsMeetingHDDPerDayThreshold(MeterBase):
    """Counts the number of periods meeting a particular heating degree day
    threshold.

    Parameters
    ----------
    base : int or float
        The heating degree day base.
    temperature_unit_str : {"degF", "degC"}
        A string denoting the temperature unit to be used.
    operation : {"lt", "lte", "gt", "gte"}
        A string representing the type of inequality test. (I.e. Is the
        threshold an upper or lower bound? Is the endpoint included?)
    proportion : float, optional
        A proportion multiplier for the number of hdd; defualt is 1.
        E.g. period_hdd <= proportion * hdd:
    """
    def __init__(self, base, temperature_unit_str, operation, proportion=1,
            **kwargs):
        super(NPeriodsMeetingHDDPerDayThreshold,self).__init__(**kwargs)
        self.base = base
        self.temperature_unit_str = temperature_unit_str
        self.operation = operation
        self.proportion = proportion

    def evaluate_mapped_inputs(self,consumption_data,hdd,weather_source,**kwargs):
        """Evaluates the number of periods meeting a consumption history limit
        according to data from a particular weather source.

        Parameters
        ----------
        consumption_data : eemeter.consumption.ConsumptionData
            Consumption data over which to count periods
        hdd : int or float
            The target number of HDD.
        weather_source : eemeter.weather.WeatherSourceBase
            A weather data source from a location as geographically and
            climatically close as possible to the target project.

        Returns
        -------
        out : dict
            A dictionary containing a single item keyed on "n_periods"
            containing the number of periods meeting the threshold.
        """
        n_periods = 0
        periods = consumption_data.periods()
        hdds = weather_source.hdd(periods, self.temperature_unit_str,
                self.base, per_day=True)
        for period_hdd in hdds:
            if self.operation == "lt":
                if period_hdd < self.proportion * hdd:
                    n_periods += 1
            elif self.operation == "lte":
                if period_hdd <= self.proportion * hdd:
                    n_periods += 1
            elif self.operation == "gt":
                if period_hdd > self.proportion * hdd:
                    n_periods += 1
            elif self.operation == "gte":
                if period_hdd >= self.proportion * hdd:
                    n_periods += 1
        return {"n_periods": n_periods}

class NPeriodsMeetingCDDPerDayThreshold(MeterBase):
    """Counts the number of periods meeting a particular cooling degree day
    threshold.

    Parameters
    ----------
    base : int or float
        The cooling degree day base.
    temperature_unit_str : {"degF", "degC"}
        A string denoting the temperature unit to be used.
    operation : {"lt", "lte", "gt", "gte"}
        A string representing the type of inequality test. (I.e. Is the
        threshold an upper or lower bound? Is the endpoint included?)
    proportion : float, optional
        A proportion multiplier for the number of cdd; defualt is 1.
        E.g. period_cdd <= proportion * cdd:
    """
    def __init__(self, base, temperature_unit_str, operation, proportion=1,
            **kwargs):
        super(NPeriodsMeetingCDDPerDayThreshold,self).__init__(**kwargs)
        self.base = base
        self.temperature_unit_str = temperature_unit_str
        self.operation = operation
        self.proportion = proportion

    def evaluate_mapped_inputs(self, consumption_data, cdd, weather_source,
            **kwargs):
        """Evaluates the number of periods meeting a consumption history limit
        according to data from a particular weather source.

        Parameters
        ----------
        consumption_data : eemeter.consumption.ConsumptionData
            Consumption data over which to count periods.
        cdd : int or float
            The target number of CDD.
        weather_source : eemeter.weather.WeatherSourceBase
            A weather data source from a location as geographically and
            climatically close as possible to the target project.

        Returns
        -------
        out : dict
            A dictionary containing a single item keyed on "n_periods"
            containing the number of periods meeting the threshold.
        """
        n_periods = 0
        periods = consumption_data.periods()
        cdds = weather_source.cdd(periods, self.temperature_unit_str,
                self.base, per_day=True)
        for period_cdd in cdds:
            if self.operation == "lt":
                if period_cdd < self.proportion * cdd:
                    n_periods += 1
            elif self.operation == "lte":
                if period_cdd <= self.proportion * cdd:
                    n_periods += 1
            elif self.operation == "gt":
                if period_cdd > self.proportion * cdd:
                    n_periods += 1
            elif self.operation == "gte":
                if period_cdd >= self.proportion * cdd:
                    n_periods += 1
        return {"n_periods": n_periods}

class RecentReadingMeter(MeterBase):
    """Evaluates whether or not there was a meter reading within the last n
    days

    Parameters
    ----------
    n_days : int
        The target number of days since the most recent reading.
    """
    def __init__(self, n_days, **kwargs):
        super(RecentReadingMeter, self).__init__(**kwargs)
        self.n_days = n_days

    def evaluate_mapped_inputs(self, consumption_data, since_date=None,
            **kwargs):
        """Evaluates the number of days since the last reading against the
        threshold.

        Parameters
        ----------
        consumption_data : eemeter.consumption.ConsumptionData
            Consumption data in which to find a most recent period
        since_date : datetime.datetime, optional
            The date to count from; defaults to datetime.now(pytz.utc).

        Returns
        -------
        out : dict
            A dictionary containing a single item with the key "recent_reading"
            containing True if the most recent reading is within the threshold.
        """
        if since_date is None:
            since_date = datetime.now(pytz.utc)
        dt_target = since_date - timedelta(days=self.n_days)
        recent_reading = any(consumption_data.data.index > dt_target)
        return {"recent_reading": recent_reading}

class CVRMSE(MeterBase):
    """Coefficient of Variation of Root-Mean-Square Error for a model fit.
    """
    def evaluate_mapped_inputs(self, y, y_hat, params, **kwargs):
        """Evaluates the Coefficient of Variation of Root-Mean-Square Error of
        a model fit.

        Parameters
        ----------
        y : array_like
            Observed values.
        y_hat : array_like
            Estimated values.
        params : array_like
            Model parameters (used only for counting the number of parameters).

        Returns
        -------
        out : dict
            - "cvrmse" : the calculated CVRMSE metric.
        """
        y_bar = np.nanmean(y)
        n = len(y)
        p = len(params)
        cvrmse = 100 * (np.nansum((y - y_hat)**2) / (n - p) )**.5 / y_bar
        return {"cvrmse": cvrmse}

class AverageDailyUsage(MeterBase):
    """Computes average daily usage given consumption.
    """

    def evaluate_mapped_inputs(self, consumption_data, fuel_unit_str,
            **kwargs):
        """Compute the average daily usage for each consumption of
        a particular fuel type.

        Parameters
        ----------
        consumption_data : eemeter.consumption.ConsumptionData
            Consumption data to draw from.
        fuel_unit_str : str
            Unit of fuel, usually "kWh" or "therms".

        Returns
        -------
        out : dict
            - "average_daily_usages": an array of average usage
              values - one value for each consumption of the given fuel type.
        """
        average_daily_consumptions, _ = \
                consumption_data.average_daily_consumptions()
        return {"average_daily_usages": average_daily_consumptions}

class EstimatedAverageDailyUsage(MeterBase):
    """Computes estmiated average daily usage given consumption, a model, and
    a weather source.

    Parameters
    ----------
    temperature_unit_str : str
        Unit of temperature, usually "degC" or "degF".
    model : eemeter.model.TemperatureSensitivityModel
        Model of energy usage for which to optimize parameter choices.
    """

    def __init__(self, temperature_unit_str, model, **kwargs):
        super(EstimatedAverageDailyUsage,self).__init__(**kwargs)
        self.temperature_unit_str = temperature_unit_str
        self.model = model

    def evaluate_mapped_inputs(self, consumption_data, weather_source,
            temp_sensitivity_params, **kwargs):
        """Compute the average daily usage for each consumption of
        a particular fuel type.

        Parameters
        ----------
        consumption_data : eemeter.consumption.ConsumptionData
            Consumption data to draw from.
        weather_source : eemeter.weather.WeatherSourceBase
            Weather data source containing data covering at least the duration
            of the consumption data.
        temp_sensitivity_params : array_like
            Parameters to use in the estimation.

        Returns
        -------
        out : dict
            - "estimated_average_daily_usages": an array of average usage
              values.
            - "n_days": the number of days in each consumption period.
        """
        periods = consumption_data.periods()
        observed_daily_temps = weather_source.daily_temperatures(periods,
                self.temperature_unit_str)
        n_days = np.array([len(temps) for temps in observed_daily_temps])
        estimated_average_daily_usages = \
                self.model.compute_usage_estimates(
                        temp_sensitivity_params, observed_daily_temps) / n_days
        return {"estimated_average_daily_usages": estimated_average_daily_usages,
                "n_days": n_days}

class RMSE(MeterBase):
    """Compute the root-mean-square error (sometimes referred to as
    root-mean-square deviation, or RMSD) of observed samples and estimated
    values.
    """
    def evaluate_mapped_inputs(self, y, y_hat, **kwargs):
        """Evaluates the Coefficient of Variation of Root-Mean-Square Error of
        a model fit.

        Parameters
        ----------
        y : array_like
            Observed values.
        y_hat : array_like
            Estimated values.

        Returns
        -------
        out : dict
            - "rmse" : the calculated RMSE metric.
        """
        n = len(y)
        rmse = (np.nansum((y - y_hat)**2) / n )**.5
        return {"rmse": rmse}

class RSquared(MeterBase):
    """Compute the r^2 metric (coefficient of determination) of observed
    samples and estimated values. Used to measure the fitness of a model.
    """
    def evaluate_mapped_inputs(self, y, y_hat, **kwargs):
        """Evaluates the r^2 fitness metric for particular samples

        Parameters
        ----------
        y : array_like
            Observed values.
        y_hat : array_like
            Estimated values.

        Returns
        -------
        out : dict
            - "r_squared" : the calculated r^2 fitness metric.
        """
        y_bar = np.nanmean(y)
        ss_residual = np.nansum( (y - y_hat)**2 )
        ss_total = np.nansum( (y - y_bar)**2 )
        r_squared = 1 - ss_residual / ss_total

        return {"r_squared": r_squared}
