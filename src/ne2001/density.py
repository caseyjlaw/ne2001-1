"Free electron density model"
import os

import numpy as np
from astropy.table import Table
from numpy import cos
from numpy import cosh
from numpy import exp
from numpy import pi
from numpy import sin
from numpy import sqrt
from numpy import tan
from scipy.integrate import quad

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


def thick_disk(xyz, r_sun, radius, height):
    """
    Calculate the contribution of the thick disk to the free electron density
     at x, y, z = `xyz`
    """
    r_ratio = sqrt(xyz[0]**2 + xyz[1]**2)/radius
    return (cos(r_ratio*pi/2)/cos(r_sun*pi/2/radius) /
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


class Class_Operation(object):
    """
    Class Operation
    """

    def __init__(self, operation, cls1, cls2):
        """
        """
        self.cls1 = cls1
        self.cls2 = cls2
        self._operation = operation

    def __getattr__(self, arg):
        return getattr(getattr(self.cls1, arg),
                       self._operation)(getattr(self.cls2, arg))


class NEobject(object):
    """
    A general electron density object
    """

    def __init__(self, xyz, func, **params):
        """

        Arguments:
        - `xyz`: Location where the electron density is calculated
        - `func`: Electron density function
        - `**params`: Model parameter
        """
        self._xyz = xyz
        self._func = func
        self._fparam = params.pop('F')
        self._ne0 = params.pop('e_density')
        self._params = params

    def __add__(self, other):
        return Class_Operation('__add__', self, other)

    def __sub__(self, other):
        return Class_Operation('__sub_', self, other)

    def __mul__(self, other):
        return Class_Operation('__mul_', self, other)

    def DM(self, xyz_sun, filter=None):
        """
        Calculate the dispersion measure at location `xyz`
        """
        n = 1000
        try:
            xyz = self.xyz - xyz_sun
        except ValueError:
            xyz = self.xyz - xyz_sun[:, None]

        dfinal = sqrt(np.sum(xyz**2, axis=0))

        if filter is None:
            return quad(lambda x: self._func(xyz_sun + x*xyz, **self._params),
                        0, 1)[0]*dfinal*1000*self._ne0

        else:
            return (dfinal*1000*self._ne0 *
                    sum([quad(lambda x: self._func(xyz_sun + x*xyz,
                                                   **self._params),
                              ii/n, (ii+1)/n)[0] for ii in range(n)
                         if filter(xyz_sun + (2*ii + 1)*xyz/n/2)]))

    @property
    def xyz(self):
        "Location where the electron density will be calculated"
        return self._xyz

    @property
    def electron_density(self):
        "Electron density at the location `xyz`"
        try:
            return self._ne
        except AttributeError:
            self._ne = self._ne0*self._func(self.xyz, **self._params)
        return self._ne

    @property
    def wight(self):
        """
        Is this object contributing to the electron density
        at the location `xyz`
        """
        return self.electron_density > 0

    @property
    def w(self):
        return self.wight

    @property
    def ne(self):
        return self.electron_density

    @wight.setter
    def wight(self, wight):
        """
        Is this object contributing to the electron density
        at the location `xyz`
        """
        self._ne = self.ne*wight

    @property
    def F(self):
        "Fluctuation parameter"
        return self.wight*self._fparam


class LocalISM(object):
    """
    Calculate the contribution of the local ISM
    to the free electron density at x, y, z = `xyz`
    """

    def __init__(self, xyz, **params):
        """
        """
        self.xyz = xyz
        self.ldr = NEobject(xyz, in_ellipsoid, **params['ldr'])
        self.lsb = NEobject(xyz, in_ellipsoid, **params['lsb'])
        self.lhb = NEobject(xyz, in_cylinder, **params['lhb'])
        self.loop_in = NEobject(xyz, in_half_sphere, **params['loop_in'])
        self.loop_out = NEobject(xyz, in_half_sphere, **params['loop_out'])
        self.loop_out.wight = ~self.loop_in.w
        self.loop = self.loop_in + self.loop_out

    @property
    def electron_density(self):
        """
        Calculate the contribution of the local ISM to the free
        electron density at x, y, z = `xyz`
        """

        try:
            return self._nelism
        except AttributeError:
            self._nelism = (self.lhb.ne +
                            (self.loop.ne +
                             (self.lsb.ne + self.ldr.ne*~self.lsb.w) *
                             ~self.loop.w)*~self.lhb.w)

        return self._nelism

    @property
    def flism(self):
        try:
            return self._flism
        except AttributeError:
            self._flism = (self.lhb.F + ~self.lhb.w *
                           (self.loop.F + ~self.loop.w *
                            (self.lsb.F + self.ldr.F*~self.lsb.w)))

        return self._flism

    @property
    def wlism(self):
        # This should be equivalent to ne>0
        # TODO: Check this!
        return np.maximum(self.loop.w,
                          np.maximum(self.ldr.w,
                                     np.maximum(self.lsb.w, self.lhb.w)))


def in_ellipsoid(xyz, center, ellipsoid, theta):
    """
    Test if xyz in the ellipsoid
    Theta in radians
    """
    try:
        xyz = xyz - center
    except ValueError:
        xyz = xyz - center[:, None]
        ellipsoid = ellipsoid[:, None]

    rot = rotation(theta, -1)
    xyz = rot.dot(xyz)

    xyz_p = xyz/ellipsoid

    return np.sum(xyz_p**2, axis=0) <= 1


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


class Clumps(object):
    """
    """

    def __init__(self, clumps_file=None):
        """
        """
        if not clumps_file:
            this_dir, _ = os.path.split(__file__)
            clumps_file = os.path.join(this_dir, "data", "neclumpN.NE2001.dat")
        self._data = Table.read(clumps_file, format='ascii')

    @property
    def use_clump(self):
        """
        """
        return self._data['flag'] == 0

    @property
    def xyz(self):
        """
        """
        try:
            return self._xyz
        except AttributeError:
            self._xyz = self.get_xyz()
        return self._xyz

    @property
    def gl(self):
        """
        Galactic longitude (deg)
        """
        return self._data['l']

    @property
    def gb(self):
        """
        Galactic latitude (deg)
        """
        return self._data['b']

    @property
    def distance(self):
        """
        Distance from the sun (kpc)
        """
        return self._data['dc']

    @property
    def radius(self):
        """
        Radius of the clump (kpc)
        """
        return self._data['rc']

    @property
    def ne(self):
        """
        Electron density of each clump (cm^{-3})
        """
        return self._data['nec']

    @property
    def edge(self):
        """
        Clump edge
        0 => use exponential rolloff out to 5 clump radii
        1 => uniform and truncated at 1/e clump radius
        """
        return self._data['edge']

    def get_xyz(self, rsun=8.5):
        """
        """
        # xyz = SkyCoord(frame="galactic", l=self.gl, b=self.gb,
        #                distance=self.distance,
        #                z_sun = z_sun*us.kpc,
        #                unit="deg, deg, kpc").galactocentric.
        #                                      cartesian.xyz.value
        # return xyz

        slc = sin(self.gl/180*pi)
        clc = cos(self.gl/180*pi)
        sbc = sin(self.gb/180*pi)
        cbc = cos(self.gb/180*pi)
        rgalc = self.distance*cbc
        xc = rgalc*slc
        yc = rsun-rgalc*clc
        zc = self.distance*sbc
        return np.array([xc, yc, zc])

    def clump_factor(self, xyz):
        """
        Clump edge
        0 => use exponential rolloff out to 5 clump radii
        1 => uniform and truncated at 1/e clump radius
        """
        if xyz.ndim == 1:
            xyz = xyz[:, None] - self.xyz
        else:
            xyz = xyz[:, :, None] - self.xyz[:, None, :]

        q2 = (np.sum(xyz**2, axis=0) /
              self.radius**2)
        # NOTE: In the original NE2001 code q2 <= 5 is used instead of q <= 5.
        # TODO: check this
        return (q2 <= 1)*(self.edge == 1) + (q2 <= 5)*(self.edge == 0)*exp(-q2)

    def ne_clumps(self, xyz):
        """
        The contribution of the clumps to the free
        electron density at x, y, z = `xyz`
        """
        return np.sum(self.clump_factor(xyz)*self.ne*self.use_clump, axis=-1)


class Voids(object):
    """
    """

    def __init__(self, voids_file=None):
        """
        """
        if not voids_file:
            this_dir, _ = os.path.split(__file__)
            voids_file = os.path.join(this_dir, "data", "nevoidN.NE2001.dat")
        self._data = Table.read(voids_file, format='ascii')

    @property
    def use_void(self):
        """
        """
        return self._data['flag'] == 0

    @property
    def xyz(self):
        """
        """
        try:
            return self._xyz
        except AttributeError:
            self._xyz = self.get_xyz()
        return self._xyz

    @property
    def gl(self):
        """
        Galactic longitude (deg)
        """
        return self._data['l']

    @property
    def gb(self):
        """
        Galactic latitude (deg)
        """
        return self._data['b']

    @property
    def distance(self):
        """
        Distance from the sun (kpc)
        """
        return self._data['dv']

    @property
    def ellipsoid_abc(self):
        """
        Void axis
        """
        return np.array([self._data['aav'],
                         self._data['bbv'],
                         self._data['ccv']])

    @property
    def rotation_y(self):
        """
        Rotation around the y axis
        """
        return [rotation(theta*pi/180, 1) for theta in self._data['thvy']]

    @property
    def rotation_z(self):
        """
        Rotation around the z axis
        """
        return [rotation(theta*pi/180, -1) for theta in self._data['thvz']]

    @property
    def ne(self):
        """
        Electron density of each void (cm^{-3})
        """
        return self._data['nev']

    @property
    def edge(self):
        """
        Void edge
        0 => use exponential rolloff out to 5 clump radii
        1 => uniform and truncated at 1/e clump radius
        """
        return self._data['edge']

    def get_xyz(self, rsun=8.5):
        """
        """
        # xyz = SkyCoord(frame="galactic", l=self.gl, b=self.gb,
        #                distance=self.distance,
        #                z_sun = z_sun*us.kpc,
        #                unit="deg, deg, kpc").galactocentric.
        #                cartesian.xyz.value
        # return xyz

        slc = sin(self.gl/180*pi)
        clc = cos(self.gl/180*pi)
        sbc = sin(self.gb/180*pi)
        cbc = cos(self.gb/180*pi)
        rgalc = self.distance*cbc
        xc = rgalc*slc
        yc = rsun-rgalc*clc
        zc = self.distance*sbc
        return np.array([xc, yc, zc])

    def void_factor(self, xyz):
        """
        Clump edge
        0 => use exponential rolloff out to 5 clump radii
        1 => uniform and truncated at 1/e clump radius
        """
        if xyz.ndim == 1:
            xyz = xyz[:, None] - self.xyz
            ellipsoid_abc = self.ellipsoid_abc
        else:
            xyz = xyz[:, :, None] - self.xyz[:, None, :]
            ellipsoid_abc = self.ellipsoid_abc[:, None, :]

        xyz = np.array([Rz.dot(Ry).dot(XYZ.T).T
                        for Rz, Ry, XYZ in
                        zip(self.rotation_z, self.rotation_y, xyz.T)]).T

        q2 = np.sum(xyz**2 / ellipsoid_abc**2, axis=0)
        # NOTE: In the original NE2001 code q2 <= 5 is used instead of q <= 5.
        # TODO: check this
        return (q2 <= 1)*(self.edge == 1) + (q2 <= 5)*(self.edge == 0)*exp(-q2)

    def ne_voids(self, xyz):
        """
        The contribution of the clumps to the free
        electron density at x, y, z = `xyz`
        """
        return np.sum(self.void_factor(xyz)*self.ne*self.use_void, axis=-1)


def rotation(theta, axis=-1):
    """
    Return a rotation matrix around axis
    0:x, 1:y, 2:z
    """
    ct = cos(theta)
    st = sin(theta)

    if axis in (0, -3):
        return np.array([[1, 0, 0],
                         [0, ct, st],
                         [0, -st, ct]])

    if axis in (1, -2):
        return np.array([[ct, 0, st],
                         [0, 1, 0],
                         [-st, 0, ct]])

    if axis in (2, -1):
        return np.array([[ct, st, 0],
                         [-st, ct, 0],
                         [0, 0, 1]])


def galactic_to_galactocentric(l, b, distance, rsun):
    slc = sin(l/180*pi)
    clc = cos(l/180*pi)
    sbc = sin(b/180*pi)
    cbc = cos(b/180*pi)
    rgalc = distance*cbc
    xc = rgalc*slc
    yc = rsun-rgalc*clc
    zc = distance*sbc
    return np.array([xc, yc, zc])
