# Module for the BNL image processing project
# Developed at the NSLS-II, Brookhaven National Laboratory
# Developed by Gabriel Iltis, Nov. 2013
"""
This function reads an AmiraMesh binary file and returns a set of two objects.
First, a numpy array containing the image data set, and second, a metadata dictionary
containing all header information both pertaining to the image data set, and required
to write the image data set back in AmiraMesh file format.
"""

import numpy as np
import os
import logging
import re

def decode_rle( d, uncompressed_size ):
    # based on decode.rle from nat's amiramesh-io.R
    d = np.fromstring(d, dtype=np.uint8 )
    rval = np.empty( (uncompressed_size,), dtype=np.uint8 )
    bytes_read = 0
    filepos = 0
    while bytes_read < uncompressed_size:
        x=d[filepos]
        if x==0:
            raise ValueError('x is 0 at %d'%filepos)
        filepos += 1

        if x > 0x7f:
            x = (x & 0x7f)
            mybytes=d[filepos:filepos+x]
            filepos += x
        else:
            mybytes=np.repeat(d[filepos],x)
            filepos += 1
        rval[bytes_read:bytes_read+len(mybytes)] = mybytes
        bytes_read += len(mybytes)
    return rval

def _read_amira(src_file):
    """
    This function reads all information contained within standard AmiraMesh
    data sets, and separates the header information from actual image, or 
    volume, data. The function then outputs two lists of strings. The first, 
    am_header, contains all of the raw header information. The second, am_data,
    contains the raw image data.
    NOTE: Both function outputs will require additional processing in order to
    be usable in python and/or with the NSLS-2 function library.
    
    Parameters
    ----------
    src_file : str
        The path and file name pointing to the AmiraMesh file to be loaded.
    
    
    Returns
    -------
    am_header : list of strings
        This list contains all of the raw information contained in the AmiraMesh
        file header. Each line of the original header has been read and stored
        directly from the source file, and will need some additional processing
        in order to be useful in the analysis of the data using the NSLS-2 
        image processing function set.
    
    am_data : str
        A compiled string containing all of the image array data, that was stored
        in the source AmiraMesh data file.  
    """
    
    am_header = []
    am_data = []
    with open(os.path.normpath(src_file), 'r') as input_file:
        while True:
            line = input_file.readline()
            am_header.append(line)
            if (line == '# Data section follows\n'):
                input_file.readline()
                break
        am_data = input_file.read()
    return am_header, am_data


def _amira_data_to_numpy(am_data, header_dict, flip_z=True):
    """
    This function takes the data object generated by "_read_amira", which 
    contains all of the image array data formated as a string and converts the 
    string into a numpy array of the dtype stipulated in the AmiraMesh header 
    dictionary.  The standard format for Avizo Binary files is IEEE binary. 
    Big or little endian-ness is stipulated in the header information, and is 
    be assessed and taken into account by this function as well, during the 
    conversion process.
    
    Parameters
    ----------
    am_data : str
        String object containing all of the image array data, formatted as IEEE 
        binary. Current dType options include:
            float
            short
            ushort
            byte
    
    header_dict : dict
        Metadata dictionary containing all relevant attributes pertaining to the
        image array. This metadata dictionary is the output from the function 
        "_create_md_dict."
    
    flip_z : bool
        This option is included because the .am data sets evaluated thus far
        have opposite z-axis indexing than numpy arrays. This switch currently
        defaults to "True" in order to ensure that z-axis indexing remains
        consistent with data processed using Avizo.
        Setting this switch to "True" will flip the z-axis during processing,
        and a value of "False" will keep the array is initially assigned during 
        the array reshaping step.
    
    Returns
    -------
    output : ndarray
        Numpy ndarray containing the image data converted from the AmiraMesh
        file. This data array is ready for further processing using the NSLS-II
        function library, or other operations able to operate on numpy arrays.
    """
    Zdim = header_dict['array_dimensions']['z_dimension']
    Ydim = header_dict['array_dimensions']['y_dimension']
    Xdim = header_dict['array_dimensions']['x_dimension']
    #Strip out null characters from the string of binary values
        # data_strip = am_data.translate(None, '\n')
    #Dictionary of the encoding types for AmiraMesh files
    am_format_dict = {'BINARY-LITTLE-ENDIAN' : '<',
                      'BINARY' : '>',
                      'ASCII' : 'unknown'
                     }
    #Dictionary of the data types encountered so far in AmiraMesh files
    am_dtype_dict = {'float': 'f4',
                     'short': 'h4',
                     'ushort': 'H4',
                     'byte': 'b'
                         }
    # Had to split out the stripping of new line characters and conversion
    # of the original string data based on whether source data is BINARY 
    # format or ASCII format. These format types require different stripping 
    # tools and different string conversion tools.
    if header_dict['data_format'] == 'BINARY-LITTLE-ENDIAN':
        assert header_dict['encoding'] == 'raw'
        data_strip = am_data.strip('\n')
        flt_values = np.fromstring(data_strip, 
                                   (am_format_dict[header_dict['data_format']] + 
                                       am_dtype_dict[header_dict['data_type']]))
    elif header_dict['data_format'] == 'BINARY':
        if header_dict['encoding'] == 'raw':
            if header_dict['data_type'] != 'byte':
                raise NotImplementedError('unsupported data type %r for format %r'%(
                    header_dict['data_type'],header_dict['data_format']))
            data_strip = am_data.strip('\n')
        else:
            enc = header_dict['encoding']
            enc_re = re.compile(r'@1\(HxByteRLE,?(\d+)\)')
            matchobj = enc_re.match( enc )
            assert matchobj is not None
            num_bytes = int(matchobj.groups()[0])

            data_rle = am_data.strip('\n')
            assert len(data_rle)==num_bytes

            assert header_dict['data_type'] == 'byte'
            uncompressed_size = Zdim*Ydim*Xdim
            data_strip = decode_rle( data_rle, uncompressed_size )
        flt_values = np.fromstring(data_strip, dtype=np.uint8) # only tested with bytes

    elif header_dict['data_format'] == 'ASCII':
        assert header_dict['encoding'] == 'raw'
        data_strip = am_data.translate(None, '\n')
        string_list = data_strip.split(" ")
        string_list = string_list[0:(len(string_list)-2)]
        flt_values = np.array(string_list).astype(am_dtype_dict[header_dict['data_type']])
    else:
        raise NotImplementedError('unknown data_format: %r'%header_dict['data_format'])
    # Resize the 1D array to the correct ndarray dimensions
    flt_values.resize(Zdim, Ydim, Xdim)
    if flip_z == True:
        output = flt_values[::-1, ..., ...]
    else:
        output = flt_values
    return output


def _clean_amira_header(header_list):
    """
    This function takes the raw string list containing the AmiraMesh header
    informationa and strips the string list of all "empty" characters,
    including new line characters ('\n') and empty lines. The function also
    splits each header line (which originally is stored as a single string)
    into individual words, numbers or characters, using spaces between words as
    the separating operator. The output of this function is used to generate
    the metadata dictionary for the image data set.

    Parameters
    ----------
    header_list : list of strings
        This is the header output from the function _read_amira()
    
    Returns
    -------
    header_list : list of strings
        This header list has been stripped and sorted and is now ready for
        populating the metadata dictionary for the image data set.
    """
    clean_header = []
    for row in header_list:
        split_header = filter(None, [word.translate(None, ',"') 
            for word in row.strip('\n').split()])
        clean_header.append(split_header)
    return clean_header

def _create_md_dict(clean_header):
    """
    This function takes the sorted header list as input and populates the
    metadata dictionary containing all relevant header information pertinent to
    the image data set originally stored in the AmiraMesh file.

    Parameters
    ----------
    header_list : list of strings
        This is the output from the _sort_amira_header function.
    
    """

    md_dict = {'software_src': clean_header[0][1], #Avizo specific
               'data_format': clean_header[0][2], #Avizo specific
               'data_format_version': clean_header[0][3] #Avizo specific
                }
    if md_dict['data_format'] == '3D':
        md_dict['data_format'] = clean_header[0][3]
        md_dict['data_format_version'] = clean_header[0][4]
    
    for header_line in clean_header:
        if 'define' in header_line:
            md_dict['array_dimensions'] = {
                    'x_dimension' : int(header_line[header_line
                        .index('define') + 2]),
                    'y_dimension' : int(header_line[header_line
                        .index('define') + 3]),
                    'z_dimension' : int(header_line[header_line
                        .index('define') + 4])
                    }
        elif 'Content' in header_line:
            md_dict['data_type'] = header_line[header_line
                    .index('Content') + 2]
        elif 'CoordType' in header_line:
            md_dict['coord_type'] = header_line[header_line
                    .index('CoordType') + 1]
        elif 'BoundingBox' in header_line:
            md_dict['bounding_box'] = {
                    'x_min': float(header_line[header_line
                        .index('BoundingBox') + 1]),
                    'x_max': float(header_line[header_line
                        .index('BoundingBox') + 2]),
                    'y_min': float(header_line[header_line
                        .index('BoundingBox') + 3]),
                    'y_max': float(header_line[header_line
                        .index('BoundingBox') + 4]),
                    'z_min': float(header_line[header_line
                        .index('BoundingBox') + 5]),
                    'z_max': float(header_line[header_line
                        .index('BoundingBox') + 6])
                    }
            
            #Parameter definition for voxel resolution calculations
            bbox = [md_dict['bounding_box']['x_min'], 
                    md_dict['bounding_box']['x_max'],
                    md_dict['bounding_box']['y_min'],
                    md_dict['bounding_box']['y_max'],
                    md_dict['bounding_box']['z_min'],
                    md_dict['bounding_box']['z_max']]
            dims = [md_dict['array_dimensions']['x_dimension'],
                    md_dict['array_dimensions']['y_dimension'],
                    md_dict['array_dimensions']['z_dimension']]
            
            #Voxel resolution calculation
            resolution_list = []
            for index in np.arange(len(dims)):
                if dims[index] > 1:
                    resolution_list.append((bbox[(2*index+1)] - 
                        bbox[(2*index)]) / (dims[index] - 1))
                else:
                    resolution_list.append(0)
                #isotropy determination (isotropic res, or anisotropic res)
            if (resolution_list[1]/resolution_list[0] > 0.99 and
                            resolution_list[2]/resolution_list[0] > 0.99 and
                            resolution_list[1]/resolution_list[0] < 1.01 and
                            resolution_list[2]/resolution_list[0] < 1.01):
                md_dict['resolution'] = {'zyx_value': resolution_list[0],
                                         'type': 'isotropic'}
            else:
                md_dict['resolution'] = {'zyx_value':
                                             (resolution_list[2],
                                              resolution_list[1],
                                              resolution_list[0]),
                                         'type': 'anisotropic'}
            
        elif 'Units' in header_line:
            try:
                md_dict['units'] = str(header_line[header_line
                                                       .index('Units') + 2])
            except:
                logging.debug('Units value undefined in source data set. '
                        'Reverting to default units value of pixels')
                md_dict['units'] = 'pixels'
        elif 'Coordinates' in header_line:
            md_dict['coordinates'] = str(header_line[header_line
                    .index('Coordinates') + 1])
        elif len(header_line)>=1 and header_line[0]=='Lattice':
            usual = ['Lattice', '{', 'byte', 'Data', '}', '@1']
            is_usual=True
            for i in range(len(usual)):
                if usual[i]!=header_line[i]:
                    is_usual=False
            if is_usual:
                md_dict['encoding'] = 'raw'
            else:
                # e.g. ['Lattice', '{', 'byte', 'Labels', '}', '@1(HxByteRLE1803306)']
                assert header_line[1]=='{'
                assert header_line[2]=='byte'
                assert header_line[3]=='Labels'
                assert header_line[4]=='}'
                md_dict['encoding'] = header_line[5]
    return md_dict


def load_amiramesh(file_path):
    """
    This function will load and convert an AmiraMesh binary file to a numpy 
    array. All pertinent information contained in the .am header file is written
    to a metadata dictionary, which is returned along with the numpy array 
    containing the image data.
    
    Parameters
    ----------
    file_path : str
        The path and file name of the AmiraMesh file to be loaded.
    
    Returns
    -------
    md_dict : dict
        Dictionary containing all pertinent header information associated with 
        the data set.
    
    np_array : ndarray
        An ndarray containing the image data set to be loaded. Values contained 
        in the resulting volume are set to be of float data type by default.
    """
    
    header, data = _read_amira(file_path)
    clean_header = _clean_amira_header(header)
    md_dict = _create_md_dict(clean_header)
    np_array = _amira_data_to_numpy(data, md_dict)
    return md_dict, np_array


