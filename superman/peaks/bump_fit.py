from __future__ import print_function, absolute_import, division
import numpy as np
import scipy.optimize
import scipy.integrate
from six.moves import xrange

from .common import PeakFinder


class BumpFit(PeakFinder):
  def __init__(self, max_peaks=None, peak_percentile=80,
               fit_kind='lorentzian', max_iter=10):
    self._max_peaks = max_peaks
    self._peak_percentile = peak_percentile
    self._fit_kind = fit_kind
    self._max_iter = max_iter

  def _fit_one(self, bands, intensities):
    max_peaks = self._max_peaks if self._max_peaks is not None else len(bands)
    cutoff = np.percentile(intensities, self._peak_percentile)
    Y = intensities.copy()
    max_idx = np.argmax(Y)
    ret = []
    for _ in xrange(max_peaks):
      peak_mask, peak_y, peak_data = fit_single_peak(
          bands, intensities, bands[max_idx], fit_kind=self._fit_kind,
          max_iter=self._max_iter, log_fn=_dummy)
      ret.append(peak_data['center'])
      Y[peak_mask] -= peak_y
      max_idx = np.argmax(Y)
      if Y[max_idx] < cutoff:
        break
    return np.array(ret)


def fit_single_peak(bands, intensities, loc, fit_kind='lorentzian',
                    max_iter=10, log_fn=print, band_resolution=1):
  if fit_kind == 'lorentzian':
    fit_func = _lorentzian
  elif fit_kind == 'gaussian':
    fit_func = _gaussian
  else:
    raise ValueError('Unsupported fit_kind: %s' % fit_kind)
  # deal with bad scaling
  scale = intensities.max()
  if scale >= 100:
    intensities = intensities / scale
  else:
    scale = 1
  # Choose reasonable starting parameters: (loc, area, fwhm)
  idx = np.searchsorted(bands, loc)
  i, j = max(0, idx-4), idx+5
  area_guess = scipy.integrate.trapz(intensities[i:j], bands[i:j])
  params = (loc, max(0, area_guess), 2 * band_resolution)
  log_fn('Starting %s: params=%s' % (fit_kind, params))
  # supply loose bounds
  # bounds = ([bands.min(), 0, 0], [bands.max(), np.inf, np.inf])
  # Keep fitting until the loc (x0) converges
  for i in xrange(max_iter):
    # Weight the channels based on distance from the approx. peak loc
    w = 1 + ((bands - loc)/band_resolution)**2
    params, pcov = curve_fit(fit_func, bands, intensities,
                             p0=params, sigma=w)  # bounds=bounds)
    log_fn('%s fit #%d: params=%s' % (fit_kind, i+1, params.tolist()))
    fit_data = fit_func(bands, *params)
    # Check for convergence in peak location
    if abs(loc - params[0]) < 1.0:
      break
    loc = params[0]
  else:
    log_fn('_fit_single_peak failed to converge in %d iterations' % max_iter)
  # Select channels in the top 99% of intensity
  cutoff = fit_data.min()*0.99 + fit_data.max()*0.01
  mask = fit_data > cutoff
  peak_x = bands[mask]
  peak_y = scale * fit_data[mask]
  # Calculate peak info
  loc, area, fwhm = map(float, params)
  loc_std, area_std, fwhm_std = map(float, np.sqrt(np.diag(pcov)))
  area *= scale
  area_std *= scale
  peak_data = dict(xmin=float(peak_x[0]), xmax=float(peak_x[-1]),
                   height=float(fit_func(loc, loc, area, fwhm)),
                   center=loc, area=area, fwhm=fwhm, center_std=loc_std,
                   area_std=area_std, fwhm_std=fwhm_std)
  return mask, peak_y, peak_data


def _lorentzian(x, x0, A, w):
  return (2*A*w)/(np.pi*(4*(x-x0)**2+w**2))


def _gaussian(x, x0, A, w):
  c = 4 * np.log(2)
  return A*np.exp(-c*(x-x0)**2/w**2)/(w*np.sqrt(np.pi/c))


def _dummy(*args, **kwargs):
  pass


# Scipy v0.17+ has bounds for curve_fit
try:
  scipy.optimize.curve_fit(lambda x,a: x+a, [0,1], [0,1], p0=(0,), bounds=(0,1))
except TypeError:
  def curve_fit(*args, **kwargs):
    if 'bounds' in kwargs:
      del kwargs['bounds']
    return scipy.optimize.curve_fit(*args, **kwargs)
else:
  curve_fit = scipy.optimize.curve_fit
