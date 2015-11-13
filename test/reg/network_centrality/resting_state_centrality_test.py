# test/reg/network_centrality/resting_state_centrality_test.py
#
# Contributing authors (please append):
# Daniel Clark
from CPAC.network_centrality.network_centrality import create_network_centrality_wf
from CPAC.network_centrality.utils import convert_pvalue_to_r

'''
This module performs regression testing on the outputs from the network
centrality workflow in
CPAC/network_centrality/resting_state_centrality.py
'''

# Collect test outputs and compare
def compare_results(out_dir, pass_thr):
    '''
    Function to collect the precomputed and test outputs and
    compare the images
    '''

    # Import packages
    import glob
    import logging
    import os
    import nibabel as nb
    import nose
    import numpy as np

    # Init variables
    outputs_to_test = {}
    test_dir = out_dir.replace('output', 'test')

    # Get logger
    cent_test_log = logging.getLogger('cent_test_log')

    # Grab precomputed outputs and corresponding test outputs
    niis = glob.glob(os.path.join(out_dir, '*.nii.gz'))

    # For each precomputed output nifti
    for nii in niis:
        nii_file = os.path.basename(nii)
        f_list = []
        # Collect test outputs
        for root, dirs, files in os.walk(test_dir):
            if files:
                f_list.extend([os.path.join(root, file) for file in files \
                          if file == nii_file])

        # If found more than one matching file for the nifti, raise Exception
        if len(f_list) == 0:
            cent_test_log.info('No test outputs found for %s, skipping ' \
                               'comparison' % nii_file)
        # Otherwise, add to test dictionary
        else:
            outputs_to_test[nii] = f_list[0]

    # Iterate through dictionary and assert correlations\
    err_msg = 'Test failed: correlation < %.3f' % pass_thr
    for precomp, test in outputs_to_test.items():
        # Load in pre-computed and test images for comparison
        img1 = nb.load(precomp).get_data()
        img2 = nb.load(test).get_data()

        # Compute pearson correlation on flattened 4D images
        cent_test_log.info('Comparing %s outputs...' % \
                           (os.path.basename(test.rstrip('.nii.gz'))))
        corr = np.corrcoef(img1.flatten(), img2.flatten())[0,1]
        cent_test_log.info('Correlation = %.3f' % corr)

        # Assert the correlation is >= pass_threshold
        nose.tools.assert_greater_equal(corr, pass_thr, err_msg)


# Get centrality workflow parameters
def get_wflow_params(reg_type):
    '''
    Function to get basic running parameters for the centrality
    workflows

    Parameters
    ----------
    reg_type : string
        registration sub-folder to set as the base directory of the
        centrality workflows

    Returns
    -------
    func_mni : string
        filepath to the resampled functional mni input to workflow
    mask_template : string
        filepath to the centrality mask template
    ident_mat : string
        filepath to the identity matrix used in resampling input to
        template file
    memory_gb : float
        the amount of memory (GB) allocated to computing centrality
    out_dir : string
        filepath to the base directory where previous computed
        centrality outputs reside
    thr_dict : dictionary
        dictionary of the threshold values for each of the centrality
        workflow types (degree, eigenvalue, and lfcd)
    fwhm : float
        the FWHM for the Gaussian smoothing kernel
    '''

    # Import packages
    import os
    import yaml
    from CPAC.utils import test_init

    # Init variables
    # Populate config file and load it
    config_path = test_init.populate_template_config('pipeline_config')
    pipeline_config = yaml.load(open(config_path, 'r'))

    # Get workflow configuration parameters
    fwhm = pipeline_config['fwhm'][0]
    memory_gb = pipeline_config['memoryAllocatedForDegreeCentrality']

    # Get threshold values and make dictionary
    deg_thr = pipeline_config['degCorrelationThreshold']
    eig_thr = pipeline_config['eigCorrelationThreshold']
    lfcd_thr = pipeline_config['lfcdCorrelationThreshold']

    thr_dict = {'deg' : deg_thr,
                'eig' : eig_thr,
                'lfcd' : lfcd_thr}

    # Get centrality mask path and identity matrix
    ident_mat = pipeline_config['identityMatrix']
    mask_template = pipeline_config['templateSpecificationFile']

    # Get precomputed centrality files directory
    out_dirs = test_init.return_subj_measure_dirs('network_centrality')
    # Only grab registration strategy of interest
    out_dir = [reg_dir for reg_dir in out_dirs \
                if reg_dir.split('/')[-4] == reg_type][0]

    # Grab functional mni as subject input for that strategy
    func_mni_dir = out_dir.replace('network_centrality', 'functional_mni')
    func_mni = os.path.join(func_mni_dir, 'functional_mni.nii.gz')

    # Return parameters
    return func_mni, mask_template, ident_mat, memory_gb, \
           out_dir, thr_dict, fwhm


# Set up workflow
def init_wflow(func_mni, mask_template, ident_mat, memory_gb, cent_imp, run_eigen=False):
    '''
    Function which inits a nipype workflow using network_centrality's
    create_resting_state_graphs() function to be used for testing

    Parameters
    ----------
    func_mni : string
        filepath to the input image to the centrality workflow; this
        is currently the registered functional to mni, resampled to the
        mask being used
    mask_template : string
        filepath to the centrality mask
    ident_mat : string
        filepath to the identity matrix used in resampling input to
        template file
    memory_gb : float
        the amount of memory, in GB, the workflow can use during
        computation
    cent_imp : string
       either 'afni' or 'cpac' - indicating the type of centrality
       implementation to test

    Returns
    -------
    wflow : nipype.pipeline.engine.Workflow
        nipype Workflow object that runs to compute the centrality
        map; this workflow does not have all of the input parameters
        specified, just input image, mask, and allocated memory
    '''

    # Import packages
    import nipype.pipeline.engine as pe
    import nipype.interfaces.fsl as fsl

    from CPAC.network_centrality import resting_state_centrality

    # Init variables
    num_threads = 8

    # Resasmple workflow
    resamp_wflow = pe.Node(interface=fsl.FLIRT(), name='resamp_wf')
    resamp_wflow.inputs.interp = 'trilinear'
    resamp_wflow.inputs.apply_xfm = True
    resamp_wflow.inputs.in_matrix_file = ident_mat
    resamp_wflow.inputs.reference = mask_template
    resamp_wflow.inputs.in_file = func_mni
 
    # Wrapper workflow to connect the resample node to cent wflow
    wflow = pe.Workflow(name='centrality_workflow')
 
    # Centrality workflow
    # AFNI implementation
    if cent_imp == 'afni':
        cent_wflow = create_network_centrality_wf('cent_wflow', num_threads,
                                                  memory_gb, run_eigen=run_eigen)
        cent_wflow.inputs.afni_degree_centrality.mask = mask_template
        if run_eigen:
            cent_wflow.inputs.afni_eigen_centrality.mask_file = mask_template
        wflow.connect(resamp_wflow, 'out_file', cent_wflow, 'afni_degree_centrality.dataset')
    # CPAC implementation
    elif cent_imp == 'cpac':
        cent_wflow = resting_state_centrality.\
                create_resting_state_graphs(allocated_memory=memory_gb, wf_name='cent_wflow')
        cent_wflow.inputs.inputspec.template = mask_template
        wflow.connect(resamp_wflow, 'out_file', cent_wflow, 'inputspec.subject')

    # Return the workflow
    return wflow


# Run and record memory of function
def run_and_get_max_memory(func_tuple):
    '''
    Function to run and record memory usage of a function

    Parameters
    ----------
    func_tuple : tuple
        tuple contaning the function and any arguments in the form of
        (func, *args, **kwargs)

    Returns
    -------
    max_mem_gb : float
        the high watermark of memory usage by the function specified
    '''

    # Import packages
    import memory_profiler

    # Get memory
    max_mem = memory_profiler.memory_usage(func_tuple, max_usage=True)
    max_mem_gb = max_mem[0]/1024.0

    # Return memory watermark in GB
    return max_mem_gb


# Test the ants registration strategy
def run_wflow(wflow, thr_type, meth_type, test_dir, threshold, cent_imp):
    '''
    Function to run the centrality workflows for degree, eigenvector,
    and lFCD.

    Parameters
    ----------
    wflow : nipype.pipeline.engine.Workflow
        centrality workflow with subject, template, and
        allocated_memory parameters populated
    thr_type : string
        the type of thresholding to perform when creating the output
        centrality image; must be 'pval', 'sparse', or 'rval'
    meth_type : string
        the type of centrality to run; must be 'deg', 'eig', or 'lfcd'
    test_dir : string
        filepath to the base test output directory to run the workflow
        in
    threshold : float
        correlation/significance/sparsity threshold on data to use
    cent_imp : string
       either 'afni' or 'cpac' - indicating the type of centrality
       implementation to test

    Returns
    -------
    None
        this function does not return a value; it runs the workflows
        in their respective directories
    '''

    # Import packages
    import datetime
    import logging
    import os

    import nibabel as nb

    # Check parameters
    # Thresholding type
    if thr_type == 'pval':
        thr_opt = 0
    elif thr_type == 'sparse':
        thr_opt = 1
    elif thr_type == 'rval':
        thr_opt = 2
    else:
        err_msg = 'Threshold type %s not compatible' % thr_type
        raise Exception(err_msg)

    # Centrality type
    if meth_type == 'deg':
        meth_opt = 0
    elif meth_type == 'eig':
        meth_opt = 1
    elif meth_type == 'lfcd':
        meth_opt = 2
    else:
        err_msg = 'Threshold type %s not compatible' % thr_type
        raise Exception(err_msg)

    # Get logger
    cent_test_log = logging.getLogger('cent_test_log')

    # Init base directory
    wflow.base_dir = os.path.join(test_dir, thr_type, meth_type)

    if cent_imp == 'afni':
        if meth_type == 'lfcd':
            err_msg = 'lFCD is currently not implemented in AFNI. Skipping...'
            cent_test_log.info(err_msg)
            return
        wflow.inputs.cent_wflow.afni_degree_centrality.prefix = 'degree_centrality.nii.gz'
        wflow.inputs.cent_wflow.afni_degree_centrality.out_1d = 'sim_matrix.1D'
        if thr_type == 'pval':
            img = nb.load(wflow.inputs.resamp_wf.in_file).get_data()
            num_tpts = img.shape[-1]
            rthresh = convert_pvalue_to_r(threshold, num_tpts, two_tailed=False)
            wflow.inputs.cent_wflow.afni_degree_centrality.thresh = rthresh
        elif thr_type == 'sparse':
            wflow.inputs.cent_wflow.afni_degree_centrality.sparsity = threshold*100.0
        elif thr_type == 'rval':
            wflow.inputs.cent_wflow.afni_degree_centrality.thresh = threshold
    elif cent_imp == 'cpac':
        # Set up centrality workflow
        wflow.inputs.cent_wflow.inputspec.method_option = meth_opt
        wflow.inputs.cent_wflow.inputspec.weight_options = [True, True]
        wflow.inputs.cent_wflow.inputspec.threshold_option = thr_opt
        wflow.inputs.cent_wflow.inputspec.threshold = threshold

    # Time for log and run
    cent_test_log.info('starting workflow execution...')
    start = datetime.datetime.now()

    # Run workflow
    #wflow.run()
    max_mem_gb = run_and_get_max_memory((wflow.run,))

    # Get and log stats
    runtime = (datetime.datetime.now()-start).total_seconds()
    cent_test_log.info('workflow took %.3f seconds to run and %.3f GB ' \
                       'of memory' % (runtime, max_mem_gb))


# Run and test centrality
def run_and_test_centrality(reg_type, pass_thr, cent_imp):
    '''
    Function to init, run, and test the outputs of the network
    centrality workflow

    Parameters
    ----------
    reg_type : string
        the type of registration used for the functional image (in MNI)
    pass_thr : float
        the correlation threshold to be greater than to ensure the new
        centrality workflow outputs are accurate
    cent_imp : string
       either 'afni' or 'cpac' - indicating the type of centrality
       implementation to test
    '''

    # Import packages
    import logging
    import os
    from CPAC.utils import test_init

    # Init variables
    thr_types = ['pval', 'sparse', 'rval']
    meth_types = ['deg', 'eig', 'lfcd']

    # Init test log file
    log_path = os.path.join(os.getcwd(), 'centrality_test.log')
    cent_test_log = test_init.setup_test_logger('cent_test_log', log_path,
                                                logging.INFO, to_screen=True)
    cent_test_log.info('Running centrality correlations tests. Storing log ' \
                       'in %s...' % log_path)

    # Init variables
    func_mni, mask_template, ident_mat, mem_gb, out_dir, thr_dict, fwhm = \
            get_wflow_params(reg_type)

    # Log parameters
    cent_test_log.info('Centrality workflow parameters:\ninput img: %s\n' \
                       'template file: %s\nallocated memory (GB): %.3f\n' \
                       'thresholds: %s\nfwhm: %d' % \
                       (func_mni, mask_template, mem_gb, str(thr_dict), fwhm))
    # Initialize common workflow
    common_wflow = init_wflow(func_mni, mask_template, ident_mat, mem_gb, cent_imp)
    # Run the p-value, sparsity, and r-value thresholding
    test_dir = out_dir.replace('output', 'test')
    # For each threshold type
    for thr_type in thr_types:
        # For each centrality method
        for meth_type in meth_types:
            # If it's lFCD and non r-value, skip it
            if (meth_type == 'lfcd' and thr_type != 'rval'):
                cent_test_log.info('lfcd non-rvalue method is not supported' \
                                   ' skipping...')
                continue
            if meth_type == 'eig' and cent_imp == 'afni':
                # Initialize common workflow
                common_wflow = init_wflow(func_mni, mask_template, ident_mat,
                                          mem_gb, cent_imp, run_eigen=True)

            # Run workflow
            threshold = thr_dict[meth_type]
            cent_test_log.info('Running %s workflow with %s thresholding ' \
                               'with a %.3f threshold...' % \
                               (meth_type, thr_type, threshold))
            run_wflow(common_wflow, thr_type, meth_type, test_dir, threshold, cent_imp)

        # Get output directories for threshold type and compare
        out_type_dir = os.path.join(out_dir, thr_type)
        compare_results(out_type_dir, pass_thr)


# Make module executable
if __name__ == '__main__':

    # Init variables
    reg_type = 'ants'
    pass_thr = 0.98

    # Centrality implementation to test ('afni' or 'cpac')
    cent_imp = 'afni'

    # Run and test centrality
    run_and_test_centrality(reg_type, pass_thr, cent_imp)
