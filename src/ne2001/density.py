"Free electron density model"
from __future__ import division
import os
from builtins import super
from functools import partial


import numpy as np
from astropy.table import Table
from numpy import cos
from numpy import cosh
from numpy import exp
from numpy import pi
from numpy import sqrt
from numpy import tan
from scipy.integrate import cumtrapz
from scipy.integrate import quad

from .utils import galactic_to_galactocentric
from .utils import lzproperty
from .utils import rotation


# import astropy.units as us
# from astropy.coordinates import SkyCoord

# Configuration
# TODO: use to config file
# input parameters for large-scale components of NE2001 30 June '02
# flags = {'wg1': 1,
#          'wg2': 1,
#          'wga': 1,
#          'wggc': 1,
#          'wglism': 1,
#          'wgcN': 1,
#          'wgvN': 1}

# solar_params = {'Rsun': 8.3}

# spiral_arms_params = {'na': 0.028,
#                       'ha': 0.23,
#                       'wa': 0.65,
#                       'Aa': 10.5,
#                       'Fa': 5,
#                       'narm1': 0.5,
#                       'narm2': 1.2,
#                       'narm3': 1.3,
#                       'narm4': 1.0,
#                       'narm5': 0.25,
#                       'warm1': 1.0,
#                       'warm2': 1.5,
#                       'warm3': 1.0,
#                       'warm4': 0.8,
#                       'warm5': 1.0,
#                       'harm1': 1.0,
#                       'harm2': 0.8,
#                       'harm3': 1.3,
#                       'harm4': 1.5,
#                       'harm5': 1.0,
#                       'farm1': 1.1,
#                       'farm2': 0.3,
#                       'farm3': 0.4,
#                       'farm4': 1.5,
#                       'farm5': 0.3}

PARAMS = {
    'thick_disk': {'e_density': 0.033/0.97,
                   'height': 0.97,
                   'radius': 17.5,
                   'F': 0.18},

    'thin_disk': {'e_density': 0.08,
                  'height': 0.15,
                  'radius': 3.8,
                  'F': 120},

    'galactic_center': {'e_density': 10.0,
                        'center': np.array([-0.01, 0.0, -0.020]),
                        'radius': 0.145,
                        'height': 0.026,
                        'F': 0.6e5},

    'ldr': {'ellipsoid': np.array([1.50, .750, .50]),
            'center': np.array([1.36, 8.06, 0.0]),
            'theta': -24.2*pi/180,
            'e_density': 0.012,
            'F': 0.1},

    'lsb': {'ellipsoid': np.array([1.050, .4250, .3250]),
            'center': np.array([-0.75, 9.0, -0.05]),
            'theta': 139.*pi/180,
            'e_density': 0.016,
            'F': 0.01},

    'lhb': {'cylinder': np.array([.0850, .1000, .330]),
            'center': np.array([0.01, 8.45, 0.17]),
            'theta': 15*pi/180,
            'e_density': 0.005,
            'F': 0.01},

    'loop_in': {'center': np.array([-0.045, 8.40, 0.07]),
                'radius': 0.120,
                'e_density': 0.0125,
                'F': 0.2},

    'loop_out': {'center': np.array([-0.045, 8.40, 0.07]),
                 'radius': 0.120 + 0.060,
                 'e_density': 0.0125,
                 'F': 0.01}}

XYZ_SUN = np.array([0, 8.5, 0])
RSUN = sqrt(XYZ_SUN[0]**2 + XYZ_SUN[1]**2)


def set_xyz_sun(xyz_sun):
    global XYZ_SUN
    global RSUN

    XYZ_SUN = xyz_sun
    RSUN = sqrt(XYZ_SUN[0]**2 + XYZ_SUN[1]**2)


def thick_disk(xyz, radius, height):
    """
    Calculate the contribution of the thick disk to the free electron density
     at x, y, z = `xyz`
    """
    r_ratio = sqrt(xyz[0]**2 + xyz[1]**2)/radius
    return (cos(r_ratio*pi/2)/cos(RSUN*pi/2/radius) /
            cosh(xyz[-1]/height)**2 *
            (r_ratio < 1))


def thin_disk(xyz, radius, height):
    """
    Calculate the contribution of the thin disk to the free electron density
     at x, y, z = `xyz`
    """
    r_ratio = sqrt(xyz[0]**2 + xyz[1]**2)/radius
    return (exp(-(1 - r_ratio)**2*radius**2/1.8**2) /
            cosh(xyz[-1]/height)**2)  # Why 1.8?


def gc(xyz, center, radius, height):
    """
    Calculate the contribution of the Galactic center to the free
    electron density at x, y, z = `xyz`
    """
    # Here I'm using the expression in the NE2001 code which is inconsistent
    # with Cordes and Lazio 2011 (0207156v3) (See Table 2)
    try:
        xyz = xyz - center
    except ValueError:
        xyz = xyz - center[:, None]

    r_ratio = sqrt(xyz[0]**2 + xyz[1]**2)/radius

    # ????
    # Cordes and Lazio 2011 (0207156v3) (Table 2)
    # return ne_gc0*exp(-(r2d/rgc)**2 - (xyz[-1]/hgc)**2)
    # ????

    # Constant ne (form NE2001 code)
    return (r_ratio**2 + (xyz[-1]/height)**2 < 1)*(r_ratio <= 1)


class NEobject(object):
    """
    A general electron density object
    """

    def __init__(self, func, **params):
        """

        Arguments:
        - `xyz`: Location where the electron density is calculated
        - `func`: Electron density function
        - `**params`: Model parameter
        """
        self._params = params
        self._fparam = params.pop('F')
        self._ne0 = params.pop('e_density')
        try:
            self._func = func(**params)
        except TypeError:
            self._func = partial(func, **params)
        self._params = params

    def __add__(self, other):
        return Add(self, other)

    def __or__(self, other):
        return OR(self, other)

    def DM(self, l, b, d,
           epsrel=1e-4, epsabs=1e-6, integrator=quad, step_size=0.001,
           *arg, **kwargs):
        """
        Calculate the dispersion measure at location `xyz`
        """
        xyz = galactic_to_galactocentric(l, b, d, [0, 0, 0])

        dfinal = sqrt(np.sum(xyz**2, axis=0))
        if integrator.__name__ is 'quad':
            return integrator(lambda x: self.ne(XYZ_SUN + x*xyz),
                              0, 1, *arg, epsrel=epsrel, epsabs=epsabs,
                              **kwargs)[0]*dfinal*1000
        else:   # Assuming sapling integrator
            nsamp = max(1000, dfinal/step_size)
            x = np.linspace(0, 1, nsamp + 1)
            xyz = galactic_to_galactocentric(l, b, x*dfinal, XYZ_SUN)
            ne = self.ne(xyz)
            return integrator(ne)*dfinal*1000*x[1]

    def dist(self, l, b, DM, step_size=0.001):
        """
        Estimate the distance to an object with dispersion measure `DM`
        located at the direction `l ,b'
        """

        # Initial guess
        dist0 = DM/PARAMS['thick_disk']['e_density']/1000

        while self.DM(l, b, dist0) < DM:
            dist0 *= 2

        nsamp = max(1000, dist0/step_size)
        d_samp = np.linspace(0, dist0, nsamp + 1)
        ne_samp = self.ne(galactic_to_galactocentric(l, b, d_samp, XYZ_SUN))
        dm_samp = cumtrapz(ne_samp, dx=d_samp[1])*1000
        return np.interp(DM, dm_samp, d_samp[1:])

    def ne(self, xyz):
        "Electron density at the location `xyz`"
        return self.electron_density(xyz)

    def electron_density(self, xyz):
        "Electron density at the location `xyz`"
        return self._ne0*self._func(xyz)


class OR(NEobject):
    """
    Return A or B where A and B are instance of
    and the combined electron density is ne_A
    for all ne_A > 0 and ne_B otherwise.
    """

    def __init__(self, object1, object2):
        """
        """
        self._object1 = object1
        self._object2 = object2

    def electron_density(self, *args):
        ne1 = self._object1.ne(*args)
        ne2 = self._object2.ne(*args)
        return ne1 + ne2*(ne1 <= 0)


class Add(NEobject):
    """
    Return A + B where A and B are instance of
    and the combined electron density is ne_A + ne_B.
    """

    def __init__(self, object1, object2):
        """
        """
        self._object1 = object1
        self._object2 = object2

    def electron_density(self, *args):
        ne1 = self._object1.ne(*args)
        ne2 = self._object2.ne(*args)
        return ne1 + ne2


class LocalISM(NEobject):
    """
    Calculate the contribution of the local ISM
    to the free electron density at x, y, z = `xyz`
    """

    def __init__(self, **params):
        """
        """
        self.ldr = NEobject(in_ellipsoid, **params['ldr'])
        self.lsb = NEobject(in_ellipsoid, **params['lsb'])
        self.lhb = NEobject(in_cylinder, **params['lhb'])
        self.loop_in = NEobject(in_half_sphere, **params['loop_in'])
        self.loop_out = NEobject(in_half_sphere, **params['loop_out'])

        self.loop = self.loop_in | self.loop_out
        self._lism = (self.lhb |
                      (self.loop |
                       (self.lsb | self.ldr)))

    def electron_density(self, xyz):
        """
        Calculate the contribution of the local ISM to the free
        electron density at x, y, z = `xyz`
        """
        return self._lism.ne(xyz)


class NEobjects(NEobject):
    """
    Read objects from file
    """

    def __init__(self, objects_file):
        """
        """
        self._data = Table.read(objects_file, format='ascii')

    @lzproperty
    def use_flag(self):
        """
        A list of flags which determine which objects to use
        """
        return np.array(self._data['flag']) == 0

    @lzproperty
    def xyz(self):
        """
        The locations of the objects in Galactocentric coordinates (kpc)
        """
        return self.get_xyz()

    @lzproperty
    def gl(self):
        """
        Galactic longitude (deg)
        """
        return np.array(self._data['l'])

    @lzproperty
    def gb(self):
        """
        Galactic latitude (deg)
        """
        return np.array(self._data['b'])

    @lzproperty
    def distance(self):
        """
        Distance from the sun (kpc)
        """
        return np.array(self._data['dist'])

    @lzproperty
    def _radius2(self):
        """
        Radius^2 of each object (kpc)
        """
        return self.radius**2

    @lzproperty
    def radius(self):
        """
        Radius of each object (kpc)
        """
        return np.array(self._data['radius'])

    @lzproperty
    def ne0(self):
        """
        Electron density of each object (cm^{-3})
        """
        return np.array(self._data['ne'])

    @lzproperty
    def _ne0_use(self):
        """
        """
        return self.ne0*self.use_flag

    @lzproperty
    def edge(self):
        """
        The edge of the object
        0 => use exponential rolloff out to 5 clump radii
        1 => uniform and truncated at 1/e clump radius
        """
        return np.array(self._data['edge'])

    def get_xyz(self):
        """
        Get the location in Galactocentric coordinates
        """
        # xyz = SkyCoord(frame="galactic", l=self.gl, b=self.gb,
        #                distance=self.distance,
        #                z_sun = z_sun*us.kpc,
        #                unit="deg, deg, kpc").galactocentric.
        #                                      cartesian.xyz.value
        # return xyz
        return galactic_to_galactocentric(l=self.gl, b=self.gb,
                                          distance=self.distance,
                                          xyz_sun=XYZ_SUN)

    def _factor(self, xyz):
        """
        """
        if xyz.ndim == 1:
            return object_factor(xyz, self.xyz, self._radius2, self.edge)
        else:
            xyz = xyz[:, :, None] - self.xyz[:, None, :]

        q2 = (np.sum(xyz**2, axis=0) /
              self._radius2)
        # NOTE: In the original NE2001 code q2 <= 5 is used instead of q <= 5.
        # TODO: check this
        q5 = (q2 <= 5)*(self.edge == 0)
        res = np.zeros_like(q2)
        res[(q2 <= 1)*(self.edge == 1)] = 1
        res[q5] = exp(-q2[q5])
        return res

    def electron_density(self, xyz):
        """
        The contribution of the object to the free
        electron density at x, y, z = `xyz`
        """
        return np.sum(self._factor(xyz)*self._ne0_use, axis=-1)


class Clumps(NEobjects):
    """
    """

    def __init__(self, clumps_file=None):
        """
        """
        if not clumps_file:
            this_dir, _ = os.path.split(__file__)
            clumps_file = os.path.join(this_dir, "data", "neclumpN.NE2001.dat")
        super().__init__(clumps_file)


class Voids(NEobjects):
    """
    """

    def __init__(self, voids_file=None):
        """
        """
        if not voids_file:
            this_dir, _ = os.path.split(__file__)
            voids_file = os.path.join(this_dir, "data", "nevoidN.NE2001.dat")
        super().__init__(voids_file)

    @lzproperty
    def xyz_rot(self):
        """
        Rotated xyz
        """
        return np.array([R.dot(xyzi) for R,
                         xyzi in zip(self.rotation, self.xyz.T)]).T

    @lzproperty
    def ellipsoid_abc(self):
        """
        Void axis
        """
        return np.array([self._data['aa'],
                         self._data['bb'],
                         self._data['cc']])

    @property
    def radius(self):
        """
        """
        return 1

    @lzproperty
    def rotation(self):
        """
        Rotation and rescaling matrix
        """
        return np.array([
            (rotation(thetaz*pi/180, -1).dot(
                rotation(thetay*pi/180, 1)).T/abc).T
            for thetaz, thetay, abc
            in zip(self._data['theta_z'], self._data['theta_y'],
                   self.ellipsoid_abc.T)
        ])

    def _factor(self, xyz):
        """
        Clump edge
        0 => use exponential rolloff out to 5 clump radii
        1 => uniform and truncated at 1/e clump radius
        """
        if xyz.ndim == 1:
            return object_factor(self.rotation.dot(xyz), self.xyz_rot,
                                 self._radius2, self.edge)
        else:
            xyz = (self.rotation.dot(xyz).T - self.xyz_rot).T

            q2 = np.sum(xyz**2, axis=1).T
            # NOTE: In the original NE2001 code q2 <= 5
            # is used instead of q <= 5.
            # TODO: check thisif xyz.ndim == 1:
            return (q2 <= 1)*self.edge + (q2 <= 5)*(1-self.edge)*exp(-q2)


class ElectronDensity(NEobject):
    """
    A class holding all the elements which contribute to free electron density
    """

    def __init__(self, clumps_file=None, voids_file=None,
                 **params):
        """
        """
        self._params = params
        self._thick_disk = NEobject(thick_disk, **params['thick_disk'])
        self._thin_disk = NEobject(thin_disk, **params['thin_disk'])
        self._galactic_center = NEobject(gc, **params['galactic_center'])
        self._lism = LocalISM(**params)
        self._clumps = Clumps(clumps_file=clumps_file)
        self._voids = Voids(voids_file=voids_file)
        self._combined = ((self._voids |
                          (self._lism |
                           (self._thick_disk +
                            self._thin_disk +
                            self._galactic_center))) +
                          self._clumps)

    def electron_density(self, xyz):
        return self._combined.ne(xyz)


class Ellipsoid(object):
    """
    """

    def __init__(self, center, ellipsoid, theta):
        """
        """
        self.center = center
        self.ellipsoid = ellipsoid
        self.theta = theta

    @lzproperty
    def transform(self):
        "Rotation and rescaling matrix"
        return (rotation(self.theta, -1).T/self.ellipsoid).T

    def in_ellipsoid(self, xyz):
        """
        Test if xyz in the ellipsoid
        Theta in radians
        """
        try:
            xyz = xyz - self.center
        except ValueError:
            xyz = xyz - self.center[:, None]

        xyz = self.transform.dot(xyz)

        return np.sum(xyz**2, axis=0) <= 1


def in_ellipsoid(center, ellipsoid, theta):
    return Ellipsoid(center, ellipsoid, theta).in_ellipsoid


def in_cylinder(xyz, center, cylinder, theta):
    """
    Test if xyz in the cylinder
    Theta in radians
    """
    xyz0 = xyz.copy()
    try:
        xyz = xyz - center
    except ValueError:
        xyz = xyz - center[:, None]
        cylinder = np.vstack([cylinder]*xyz.shape[-1]).T
    xyz[1] -= tan(theta)*xyz0[-1]

    cylinder_p = cylinder.copy()
    z_c = (center[-1] - cylinder[-1])
    izz = (xyz0[-1] <= 0)*(xyz0[-1] >= z_c)
    cylinder_p[0] = (0.001 +
                     (cylinder[0] - 0.001) *
                     (1 - xyz0[-1]/z_c))*izz + cylinder[0]*(~izz)
    xyz_p = xyz/cylinder_p

    return (xyz_p[0]**2 + xyz_p[1]**2 <= 1) * (xyz_p[-1]**2 <= 1)


def in_half_sphere(xyz, center, radius):
    "Test if `xyz` in the sphere with radius r_sphere  centerd at `xyz_center`"
    xyz0 = xyz.copy()
    try:
        xyz = xyz - center
    except ValueError:
        xyz = xyz - center[:, None]
    distance = sqrt(np.sum(xyz**2, axis=0))
    return (distance <= radius)*(xyz0[-1] >= 0)


def object_factor(xyz, xyz0, r2, edge):
    """
    edge
    0 => use exponential rolloff out to 5 clump radii
    1 => uniform and truncated at 1/e clump radius
    """
    xyz = (xyz - xyz0.T).T

    q2 = (xyz[0]**2 + xyz[1]**2 + xyz[2]**2) / r2
    # NOTE: In the original NE2001 code q2 <= 5 is used instead of q <= 5.
    # TODO: check this
    q5 = (q2 <= 5)*(edge == 0)
    res = np.zeros_like(q2)
    res[(q2 <= 1)*(edge == 1)] = 1
    res[q5] = exp(-q2[q5])
    return res
