import numpy as np
from hyppo.independence.dcorr import Dcorr
from numba import jit

from ..tools import check_perm_blocks_dim, chi2_approx, compute_dist
from ._utils import _CheckInputs
from .base import ConditionalTest, ConditionalTestOutput


class PDcorr(ConditionalTest):
    r"""
    Partial Distance Correlation (Dcorr) test statistic and p-value.

    Dcorr is a measure of dependence between two paired random matrices of
    not necessarily equal dimensions. The coefficient is 0 if and only if the
    matrices are independent. It is an example of an energy distance.

    The statistic can be derived as follows:

    Let :math:`x` and :math:`y` be :math:`(n, p)` samples of random variables
    :math:`X` and :math:`Y`. Let :math:`D^x` be the :math:`n \times n`
    distance matrix of :math:`x` and :math:`D^y` be the :math:`n \times n` be
    the distance matrix of :math:`y`. The distance covariance is,

    .. math::

        \mathrm{Dcov}^b_n (x, y) = \frac{1}{n^2} \mathrm{tr} (D^x H D^y H)

    where :math:`\mathrm{tr} (\cdot)` is the trace operator and :math:`H` is
    defined as :math:`H = I - (1/n) J` where :math:`I` is the identity matrix
    and :math:`J` is a matrix of ones. The normalized version of this
    covariance is distance correlation `[1]`_ and is

    .. math::

        \mathrm{Dcorr}^b_n (x, y) = \frac{\mathrm{Dcov}^b_n (x, y)}
                                       {\sqrt{\mathrm{Dcov}^b_n (x, x)
                                              \mathrm{Dcov}^b_n (y, y)}}

    This is a biased test statistic. An unbiased alternative also exists, and is
    defined using the following: Consider the
    centering process where :math:`\mathbb{1}(\cdot)` is the indicator
    function:

    .. math::

        C^x_{ij} = \left[ D^x_{ij} - \frac{1}{n-2} \sum_{t=1}^n D^x_{it}
            - \frac{1}{n-2} \sum_{s=1}^n D^x_{sj}
            + \frac{1}{(n-1) (n-2)} \sum_{s,t=1}^n D^x_{st} \right]
            \mathbb{1}_{i \neq j}

    and similarly for :math:`C^y`. Then, this unbiased Dcorr is,

    .. math::

        \mathrm{Dcov}_n (x, y) = \frac{1}{n (n-3)} \mathrm{tr} (C^x C^y)

    The normalized version of this covariance `[2]`_ is

    .. math::

        \mathrm{Dcorr}_n (x, y) = \frac{\mathrm{Dcov}_n (x, y)}
                                        {\sqrt{\mathrm{Dcov}_n (x, x)
                                               \mathrm{Dcov}_n (y, y)}}

    The p-value returned is calculated using a permutation test using
    :meth:`hyppo.tools.perm_test`. The fast version of the test uses
    :meth:`hyppo.tools.chi2_approx`.

    When the data is 1 dimension and the distance metric is Euclidean,
    and even faster version of the algorithm is run (computational
    complexity is :math:`\mathcal{O}(n \log n)`) `[3]`_.

    .. _[1]: https://projecteuclid.org/euclid.aos/1201012979
    .. _[2]: https://projecteuclid.org/euclid.aos/1413810731
    .. _[3]: https://www.sciencedirect.com/science/article/pii/S0167947319300313

    Parameters
    ----------
    compute_distance : str, callable, or None, default: "euclidean"
        A function that computes the distance among the samples within each
        data matrix.
        Valid strings for ``compute_distance`` are, as defined in
        :func:`sklearn.metrics.pairwise_distances`,

            - From scikit-learn: [``"euclidean"``, ``"cityblock"``, ``"cosine"``,
              ``"l1"``, ``"l2"``, ``"manhattan"``] See the documentation for
              :mod:`scipy.spatial.distance` for details
              on these metrics.
            - From scipy.spatial.distance: [``"braycurtis"``, ``"canberra"``,
              ``"chebyshev"``, ``"correlation"``, ``"dice"``, ``"hamming"``,
              ``"jaccard"``, ``"kulsinski"``, ``"mahalanobis"``, ``"minkowski"``,
              ``"rogerstanimoto"``, ``"russellrao"``, ``"seuclidean"``,
              ``"sokalmichener"``, ``"sokalsneath"``, ``"sqeuclidean"``,
              ``"yule"``] See the documentation for :mod:`scipy.spatial.distance` for
              details on these metrics.

        Set to ``None`` or ``"precomputed"`` if ``x`` and ``y`` are already distance
        matrices. To call a custom function, either create the distance matrix
        before-hand or create a function of the form ``metric(x, **kwargs)``
        where ``x`` is the data matrix for which pairwise distances are
        calculated and ``**kwargs`` are extra arguements to send to your custom
        function.
    bias : bool, default: False
        Whether or not to use the biased or unbiased test statistics.
    **kwargs
        Arbitrary keyword arguments for ``compute_distance``.
    """

    def __init__(self, compute_distance="euclidean", bias=False, **kwargs):
        # set is_distance to true if compute_distance is None
        self.is_distance = False
        if not compute_distance:
            self.is_distance = True
        self.bias = bias
        self.is_fast = False
        ConditionalTest.__init__(self, compute_distance=compute_distance, **kwargs)

    def statistic(self, x, y, z):
        r"""
        Helper function that calculates the Dcorr test statistic.

        Parameters
        ----------
        x,y,z : ndarray
            Input data matrices. ``x`` and ``y`` must have the same number of
            samples. That is, the shapes must be ``(n, p)`` and ``(n, q)`` where
            `n` is the number of samples and `p` and `q` are the number of
            dimensions. Alternatively, ``x`` and ``y`` can be distance matrices,
            where the shapes must both be ``(n, n)``.

        Returns
        -------
        stat : float
            The computed Dcorr statistic.
        """
        n = x.shape[1]
        distx = x
        disty = y
        disty = z

        if not (self.is_distance or self.is_fast):
            distx, disty = compute_dist(
                x, y, metric=self.compute_distance, **self.kwargs
            )
            disty, distz = compute_dist(
                disty, z, metric=self.compute_distance, **self.kwargs
            )

        dcorr_stat = Dcorr(compute_distance=None, bias=self.bias).statistic
        a = dcorr_stat(distx, disty) - dcorr_stat(distx, distz) * dcorr_stat(
            distz, disty
        )
        b = np.sqrt(1 - dcorr_stat(distx, distz) ** 2) * np.sqrt(
            1 - dcorr_stat(disty, distz) ** 2
        )
        stat = 0 if b == 0 else a / b

        return stat

    def test(self, x, y, z, reps=1000, workers=1, auto=True, perm_blocks=None):
        r"""
        Calculates the PDcorr test statistic and p-value.

        Parameters
        ----------
        x,y,z : ndarray
            Input data matrices. ``x`` and ``y`` must have the same number of
            samples. That is, the shapes must be ``(n, p)`` and ``(n, q)`` where
            `n` is the number of samples and `p` and `q` are the number of
            dimensions. Alternatively, ``x`` and ``y`` can be distance matrices,
            where the shapes must both be ``(n, n)``.
        reps : int, default: 1000
            The number of replications used to estimate the null distribution
            when using the permutation test used to calculate the p-value.
        workers : int, default: 1
            The number of cores to parallelize the p-value computation over.
            Supply ``-1`` to use all cores available to the Process.
        auto : bool, default: True
            Automatically uses fast approximation when `n` and size of array
            is greater than 20. If ``True``, and sample size is greater than 20, then
            :class:`hyppo.tools.chi2_approx` will be run. Parameters ``reps`` and
            ``workers`` are
            irrelevant in this case. Otherwise, :class:`hyppo.tools.perm_test` will be
            run.
            If ``x`` and ``y`` have `p` equal to 1 and ``compute_distance`` set to
            ``'euclidean'``, then and :math:`\mathcal{O}(n \log n)` version is run.
        perm_blocks : None or ndarray, default: None
            Defines blocks of exchangeable samples during the permutation test.
            If None, all samples can be permuted with one another. Requires `n`
            rows. At each column, samples with matching column value are
            recursively partitioned into blocks of samples. Within each final
            block, samples are exchangeable. Blocks of samples from the same
            partition are also exchangeable between one another. If a column
            value is negative, that block is fixed and cannot be exchanged.

        Returns
        -------
        stat : float
            The computed Dcorr statistic.
        pvalue : float
            The computed Dcorr p-value.

        Examples
        --------
        >>> import numpy as np
        >>> from hyppo.independence import Dcorr
        >>> x = np.arange(25)
        >>> y = x
        >>> stat, pvalue = Dcorr().test(x, y)
        >>> '%.1f, %.2f' % (stat, pvalue)
        '1.0, 0.00'

        In addition, the inputs can be distance matrices. Using this is the,
        same as before, except the ``compute_distance`` parameter must be set
        to ``None``.

        >>> import numpy as np
        >>> from hyppo.independence import Dcorr
        >>> x = np.ones((10, 10)) - np.identity(10)
        >>> y = 2 * x
        >>> dcorr = Dcorr(compute_distance=None)
        >>> stat, pvalue = dcorr.test(x, y)
        >>> '%.1f, %.2f' % (stat, pvalue)
        '0.0, 1.00'
        """
        check_input = _CheckInputs(
            x,
            y,
            z,
            reps=reps,
        )
        x, y = check_input()
        if perm_blocks is not None:
            check_perm_blocks_dim(perm_blocks, y)

        if (
            auto
            and x.shape[1] == 1
            and y.shape[1] == 1
            and self.compute_distance == "euclidean"
        ):
            self.is_fast = True

        if auto and x.shape[0] > 20 and perm_blocks is None:
            stat, pvalue = chi2_approx(self.statistic, x, y)
            self.stat = stat
            self.pvalue = pvalue
            self.null_dist = None
        else:
            if not self.is_fast:
                x, y = compute_dist(x, y, metric=self.compute_distance, **self.kwargs)
                self.is_distance = True
            stat, pvalue = super(PDcorr, self).test(
                x,
                y,
                reps,
                workers,
                perm_blocks=perm_blocks,
                is_distsim=self.is_distance,
            )

        return ConditionalTestOutput(stat, pvalue)