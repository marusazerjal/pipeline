"""
Utilities functions to assist with reductions.

Note: When running without ssh -Y, get RuntimeError: Invalid DISPLAY variable
"""
from __future__ import print_function, division
import glob
import numpy as np
from astropy.io import fits
import sys
import os
import process_stellar as ps
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm


def extract_stellar_spectra_ascii(root, night, steps = ["08", "09", "10"]):
    """Generate ascii spectra for each of the data reduction steps in steps.
    Saves ascii spectra in a new folder in the night directory called 'ascii'.

    Parameters:
    -----------
    root: string
        The base path to the reduced data (i.e. where the nightly folders are
        stored.)
    night: string
        The night to extract spectra from (in the form 201XYYZZ).
    steps: list of strings
        The PyWiFeS data reduction steps to extract and convert to 1D spectra.
    """
    # Sort out directory structures
    data_dir = os.path.join(root, night)
    out_dir = os.path.join(data_dir, 'ascii')

    if not os.path.isdir(out_dir) and not os.path.exists(out_dir):
        os.mkdir(out_dir)

    print('Converting to ascii:', data_dir)

    # Extract all files
    for path, subdirs, files in os.walk(data_dir):
        for name in files:
            fl=os.path.join(path, name)
            step = fl.split(".")[-2][1:]

            # Only run on specified data reduction outputs
            if step in steps and fl.endswith('%s.fits' % step):
                print(fl)
                f = fits.open(fl)
                header = f[0].header
                objectid = header['OBJNAME']
                run = header['RUN']
                f.close()

                # Extract spectrum
                flux, wave = ps.read_and_find_star_p08(fl)
                spectrum, sig = ps.weighted_extract_spectrum(flux)

                # Determine output format depending on spectral arm
                if 'T2m3wr' in name:
                    filename = '%s_%s_%s_r.dat'%(night, objectid, step)
                elif 'T2m3wb' in name:
                    filename = '%s_%s_%s_b.dat'%(night, objectid, step)
                
                filename = filename.replace(' ', '_')
                
                # Save output
                fln = os.path.join(out_dir, filename)
                print(fln)
                np.savetxt(fln, np.transpose([wave, spectrum]))


def make_extracted_stellar_cube(root, night, steps = ["08", "09", "10"]):
    """Make a fits data cube of the reduced and extracted stellar spectra, with
    a different HDU for each data reduction step. Store this new cube in a 
    folder called 'extracted_1D_cubes' in the night folder. By default:
     - 8: Final (non-fluxed or telluric corrected)
     - 9: Final (fluxed)
     -10: Final (fluxed and telluric corrected)

    Parameters:
    -----------
    root: string
        The base path to the reduced data (i.e. where the nightly folders are
        stored.)
    night: string
        The night to extract spectra from (in the form 201XYYZZ).
    steps: list of strings
        The PyWiFeS data reduction steps to extract and convert to 1D spectra.
    """
    # Sort out directory structures
    data_dir = os.path.join(root, night)
    out_dir = os.path.join(data_dir, 'extracted_cubes_1d')

    if not os.path.isdir(out_dir) and not os.path.exists(out_dir):
        os.mkdir(out_dir)

    # Get a list of the of the reduced files. Assume files have the naming
    # convention T2m3w[r/b]-20190828.104313-0031.p08.fits' where [r/b] will be
    # a single character indicating the arm of WiFeS used.
    unique_obs = glob.glob(os.path.join(data_dir, "*", "*%s.fits" % steps[0]))

    # Generalise by removing the suffixes
    unique_obs = [ob.replace(".p%s.fits" % steps[0], "") for ob in unique_obs]

    # Now go through one observation at a time, and create a data cube 
    # containing the original header information, and a HDU for each step of
    # the data reduction listed in steps.
    for ob in unique_obs:
        # Get the list of fits files to extract 1D spectra from
        fits_files = [ob + ".p%s.fits" % step for step in steps]

        # Get the header information from the first
        header = fits.getheader(fits_files[0])

        obj_id = header['OBJNAME'].replace(" ","")

        # Construct a new fits file
        hdus = []
        hdus.append(fits.PrimaryHDU(header=header))

        print("Making cube for %s%s" % (ob, ".pXX.fits"))

        for fits_file, step in zip(fits_files, steps):
            # Extract the 1D spectrum
            print("\tExtracting 1D spectrum for step %s" % step)
            flux, wave = ps.read_and_find_star_p08(fits_file)
            spectrum, sig = ps.weighted_extract_spectrum(flux)

            # Make fits table from numpy record array
            data = np.array([wave, spectrum, sig]).T.tolist()
            rec = np.rec.array(data, names=["wave", "spectrum", "sigma"])

            hdus.append(fits.BinTableHDU.from_columns(rec))
            hdus[-1].header["REDSTEP"] = step
        
        # Determine output format depending on spectral arm
        if 'T2m3wr' in ob:
            output_filename = '%s_%s_r.fits' % (night, obj_id)
        elif 'T2m3wb' in ob:
            output_filename = '%s_%s_b.fits' % (night, obj_id)

        output_filepath = os.path.join(out_dir, output_filename)

        # Write the fits file
        print("Writing cube to %s \n" % output_filename)
        hdu_list = fits.HDUList(hdus)
        hdu_list.writeto(output_filepath, overwrite=True)


def update_object_header(root, night, print_only=False):
    """Quick function to sort out instances where OBJNAME header keyword is
    correct, but OBJECT keyword header is wrong (but has priority).

    Currently this looks for "exp" (i.e. exposure time) in OBJECT, due to a 
    TAROS copy-paste error

    Parameters
    ----------
    root: string
        Root directory where all the night folders are stored.

    night: string
        Name of the folder for a night's data, e.g. 20190828

    print_only: boolean
        Whether to actually change the headers, or just pring what they are
    """
    # Get a list of the files
    fits_files = glob.glob(os.path.join(root, night, "*.fits"))
    fits_files.sort()

    # For all files, open and check the state of the headers
    for fits_file in fits_files:
        with fits.open(fits_file, "update") as ff:
            if ("OBJNAME" in ff[0].header 
                and ff[0].header["IMAGETYP"]=="object"):
                if ("exp" in ff[0].header["OBJNAME"] 
                    and ff[0].header["OBJECT"] != ""):
                    print("%s: \t OBJECT: %s\t OBJNAME: %s" 
                           % (fits_file, ff[0].header["OBJECT"], 
                              ff[0].header["OBJNAME"]))
                    if not print_only:
                        ff[0].header["OBJNAME"] = ff[0].header["OBJECT"]
                        
def flat_stats():
    """
    MZ: Write the doc!!
    
    Goal: Identify bad flats.
    
    Plot masterflats and trace one line. Divide by its maximum and overplot all of them.
    What about stellar/ybin2?
    """
    
    # Folder with fits files
    #~ root = sys.argv[1]
    root='/data/mash/marusa/2m3reduced/wifes/'
    print('root', root)
    
    fig=plt.figure()
    ax=fig.add_subplot(111)

    for path, subdirs, files in os.walk(root):
        for name in files:
            fl=os.path.join(path, name)
            print(fl)
            if fl=='wifesB_super_domeflat.fits':
                print('****************'+fl)
                
                # Read data
                f=fits.open(fl)
                header = f[0].header
                f.close()
                image_data = fits.getdata(fl, ext=0)

                # Extract one line
                line = image_data[2145:2245,:]
                line = np.max(line, axis=0)
                m = np.max(line)
                line = line/m
                
                x=range(len(line))
                ax.plot(x, line)
    plt.show()
