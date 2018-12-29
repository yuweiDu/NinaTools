import os
from six.moves import urllib
import scipy.io as sio
import zipfile
import numpy as np
from abc import ABC, abstractmethod


#
# Responsible for downloading, and formatting data into X
#
class NinaDataParser:

    raw_data_dir    = "raw"
    proc_data_dir   = "processed"
    nina_data_urls  = {
                        "s1.zip": "https://zenodo.org/record/1000116/files/s1.zip?download=1",
                        "s2.zip": "https://zenodo.org/record/1000116/files/s2.zip?download=1",
                        "s3.zip": "https://zenodo.org/record/1000116/files/s3.zip?download=1",
                        "s4.zip": "https://zenodo.org/record/1000116/files/s4.zip?download=1",
                        "s5.zip": "https://zenodo.org/record/1000116/files/s5.zip?download=1",
                        "s6.zip": "https://zenodo.org/record/1000116/files/s6.zip?download=1",
                        "s7.zip": "https://zenodo.org/record/1000116/files/s7.zip?download=1",
                        "s8.zip": "https://zenodo.org/record/1000116/files/s8.zip?download=1",
                        "s9.zip": "https://zenodo.org/record/1000116/files/s9.zip?download=1",
                        "s10.zip": "https://zenodo.org/record/1000116/files/s10.zip?download=1"
                    }

    loaded_data = {}    # A dictionary with the following structure:
                        #
                        #       {
                        #           "S1": {
                        #                       "E1": {... },
                        #                       "E2": {... },
                        #                       "E3": {... }
                        #                   }
                        #
                        #           "S2:" {
                        #                       "E1": {... }, ...
                        #                   }
                        #
                        #           ...
                        #       }


    def __init__(self, all_data_path, grab_all_data = True):

        if all_data_path is None:
            raise ValueError("All data path is empty.")

        #
        # Create directory structure
        #
        if not os.path.exists(all_data_path):
            os.makedirs(all_data_path)

        self.raw_data_path   = os.path.join(all_data_path, self.raw_data_dir)
        self.proc_data_path  = os.path.join(all_data_path, self.proc_data_dir)

        if not os.path.exists(self.raw_data_path):
            os.makedirs(self.raw_data_path)
        if not os.path.exists(self.proc_data_path):
            os.makedirs(self.proc_data_path)

        #
        # Obtain Nina dataset
        #
        if grab_all_data:
            if self.miss_proc_data():
                if self.miss_raw_data():
                    self.get_raw_data()
                self.process_raw_data()


    def load_processed_data(self):

        if self.miss_proc_data():
            raise RuntimeError("Missing processed data, unable to load processed data.")

        for subdir, dirs, files in os.walk(self.proc_data_path):
            for file in files:
                if file.endswith('.mat'):
                    file_path = os.path.join(subdir, file)

                    patient = subdir.split('/')[-1]
                    if patient not in self.loaded_data:
                        self.loaded_data[patient] = {}

                    _, exercise, _ = file.split('.')[0].split('_')
                    self.loaded_data[patient][exercise] = sio.loadmat(file_path)

        return self.loaded_data


    def get_raw_data(self):
        """
            Downloads each missing zip file into the "raw" directory.
        """

        zip_files   = list(self.nina_data_urls.keys())

        for i, zip in enumerate(zip_files):
            cur_path = os.path.join(self.raw_data_path, zip)

            if not os.path.exists(cur_path):
                cur_url         = self.nina_data_urls[zip]
                http_request    = urllib.request.urlopen(cur_url)

                if http_request is None:
                    raise RuntimeError("Unable to open the following url \n{}".format(cur_url))
                else:
                    print("{}/{}. Downloading \"{}\".".format(i + 1, len(zip_files), cur_url))

                with open(cur_path, "wb") as f:
                    f.write(http_request.read())


    def process_raw_data(self):
        """
            Extracts each zip file into the "processed" directory.
        """

        for zip in self.nina_data_urls.keys():

            cur_proc_path   = os.path.join(self.proc_data_path, zip.replace(".zip", ""))

            if not os.path.exists(cur_proc_path):
                cur_zip_path    = os.path.join(self.raw_data_path, zip)
                zip_ref         = zipfile.ZipFile(cur_zip_path, 'r')

                zip_ref.extractall(self.proc_data_path)
                zip_ref.close()

    def miss_proc_data(self):
        proc_data_miss = False

        for zip in self.nina_data_urls.keys():
            cur_proc_path = os.path.join(self.proc_data_path, zip.replace(".zip", ""))
            if not os.path.exists(cur_proc_path):
                proc_data_miss = True

        return proc_data_miss

    def miss_raw_data(self):
        raw_data_miss = False

        for zip in self.nina_data_urls.keys():
            cur_path = os.path.join(self.raw_data_path, zip)
            if not os.path.exists(cur_path):
                raw_data_miss = True

        return raw_data_miss

#
# All datasets will use this interface, and implement "process_single_exercise()", "get_dataset_name()".
#
class Dataset(ABC):

    window_size     = 200
    overlap_size    = 100
    num_classes     = 52 + 1
    balance_classes = True # Will limit number of rest samples for train/test

    # Filled via "create_dataset()"
    train_features  = None
    train_labels    = None
    test_features   = None
    test_labels     = None
    all_samples     = None

    # Need to correct labels, by inspecting exercise number
    E1_classes      = 12
    E2_classes      = 17
    E3_classes      = 23
    E3_name         = "E3"
    E2_name         = "E2"
    rest_label      = 0


    def __init__(self, all_data_path, feature_extractor):

        if feature_extractor is None:
            raise ValueError("Feature extractor is empty.")
        if all_data_path is None:
            raise ValueError("All data path is empty.")

        self.feature_extractor  = feature_extractor
        self.all_data_path      = all_data_path

    def create_dataset(self, loaded_data):

        if self.feature_extractor.requires_global_setup:
            self.create_dataset_helper(loaded_data, True)

        self.create_dataset_helper(loaded_data, False)

    def create_dataset_helper(self, loaded_data, obtain_all_samples):
        """
            Converts loaded data (via NinaDataParser) into a useable, baseline dataset, consisting of:
                1. train_features
                2. train_labels
                3. test_features
                4. test_labels

        :param feature_extractor: A function that transform 200 emg samples (a window) into a single feature point.
        :param obtain_all_samples: Avoid creating a train/test split, simply obtain all samples of windowed data.
        """

        if self.load_dataset():
            return

        # To be filled
        self.train_features = []
        self.train_labels   = []
        self.test_features  = []
        self.test_labels    = []
        self.all_samples    = []

        # Class balancing
        num_samples         = 0
        num_rest_samples    = 0

        for patient in loaded_data.keys():
            for ex in loaded_data[patient].keys():
                self.process_single_exercise(loaded_data, patient, ex, num_samples,
                                                num_rest_samples, obtain_all_samples)

        # Convert to numpy arrays:
        #
        if obtain_all_samples:
            self.all_samples    = np.array(self.all_samples)
            self.feature_extractor.global_setup(self.all_samples)
        else:
            self.train_features = np.array(self.train_features)
            self.train_labels   = np.array(self.train_labels)
            self.test_features  = np.array(self.test_features)
            self.test_labels    = np.array(self.test_labels)

            # Save the above to the baseline dataset directory:
            self.save_dataset()

    def save_dataset(self):

        feat_ext_name   = self.feature_extractor.__class__.__name__
        feat_path       = os.path.join(self.all_data_path, self.get_dataset_name(), feat_ext_name)

        if not os.path.exists(feat_path):
            os.makedirs(feat_path)

        if self.train_features is not None:
            np.save(os.path.join(feat_path, "train_features"), self.train_features)
        if self.train_labels is not None:
            np.save(os.path.join(feat_path, "train_labels"), self.train_labels)
        if self.test_features is not None:
            np.save(os.path.join(feat_path, "test_features"), self.test_features)
        if self.test_labels is not None:
            np.save(os.path.join(feat_path, "test_labels"), self.test_labels)

        if ((self.train_labels is None) or (self.train_labels is None) or
            (self.test_features is None) or (self.test_labels is None)):
            raise RuntimeError("One of the dataset pieces are empty.")

    def load_dataset(self):
        """
        :return: True, if this function was able to load the baseline dataset.
        """

        feat_ext_name   = self.feature_extractor.__class__.__name__
        feat_path       = os.path.join(self.all_data_path, self.get_dataset_name(), feat_ext_name)

        if not os.path.exists(feat_path):
            return False
        if not os.path.exists(os.path.join(feat_path, "train_features.npy")):
            return False
        if not os.path.exists(os.path.join(feat_path, "train_labels.npy")):
            return False
        if not os.path.exists(os.path.join(feat_path, "test_features.npy")):
            return False
        if not os.path.exists(os.path.join(feat_path, "test_labels.npy")):
            return False

        self.train_features = np.load(os.path.join(feat_path, "train_features.npy"))
        self.train_labels   = np.load(os.path.join(feat_path, "train_labels.npy"))
        self.test_features  = np.load(os.path.join(feat_path, "test_features.npy"))
        self.test_labels    = np.load(os.path.join(feat_path, "test_labels.npy"))

        return True

    @abstractmethod
    def process_single_exercise(self, loaded_data, patient, ex, num_samples, num_rest_samples, obtain_all_samples):
        pass

    @abstractmethod
    def get_dataset_name(self):
        pass

#
# The training/validation/testing dataset described in
#   "Comparison of six electromyography acquisition setups on hand movement classification tasks"
#       by Stefano Pizzolato, et al.
#
class BaselineDataset(Dataset):

    def process_single_exercise(self, loaded_data, patient, ex, num_samples, num_rest_samples, obtain_all_samples):

        cur_data = loaded_data[patient][ex]
        num_emg = cur_data["emg"].shape[0]

        # Look for possible windows of EMG data
        #
        start_window = 0

        while (start_window + self.window_size) <= num_emg:

            window_label = int(cur_data["restimulus"][start_window][0])

            offset = 0
            while (offset < self.window_size) and (cur_data["restimulus"][start_window + offset][0] == window_label):
                offset += 1

            # Found a valid window
            #
            if offset == self.window_size:
                emg_window = cur_data["emg"][start_window:start_window + self.window_size]

                # Balance number of rest classes
                if (window_label == self.rest_label) and self.balance_classes:
                    if num_rest_samples > (num_samples / float(self.num_classes)):
                        start_window += self.overlap_size
                        continue
                    else:
                        num_rest_samples += 1
                num_samples += 1

                if obtain_all_samples:
                    win_repetition = cur_data["rerepetition"][start_window]
                    if not ((win_repetition == 2) or (win_repetition == 5)):
                        self.all_samples.append(emg_window)

                # Split into train/test:
                else:
                    win_feat = self.feature_extractor.extract_feature_point(emg_window)
                    win_repetition = cur_data["rerepetition"][start_window]

                    # Correct the window label
                    if window_label != self.rest_label:
                        if ex == self.E3_name:
                            window_label += self.E1_classes + self.E2_classes
                        elif ex == self.E2_name:
                            window_label += self.E1_classes

                    if (win_repetition == 2) or (win_repetition == 5):
                        self.test_features.append(win_feat)
                        self.test_labels.append(window_label)
                    else:
                        self.train_features.append(win_feat)
                        self.train_labels.append(window_label)

                start_window += self.overlap_size

            else:
                start_window += offset

    def get_dataset_name(self):
        return "baseline"

#
# Rather than split training/testing based on movement number, this dataset splits based on patients:
#   --> Via use of NCC (Normalized Cross Correlation), data for patients 8 and 10 are the furthest away.
#
class LogicalDatasetV1(Dataset):

    def process_single_exercise(self, loaded_data, patient, ex, num_samples, num_rest_samples, obtain_all_samples):

        cur_data = loaded_data[patient][ex]
        num_emg = cur_data["emg"].shape[0]

        # Look for possible windows of EMG data
        #
        start_window = 0

        while (start_window + self.window_size) <= num_emg:

            window_label = int(cur_data["restimulus"][start_window][0])

            offset = 0
            while (offset < self.window_size) and (cur_data["restimulus"][start_window + offset][0] == window_label):
                offset += 1

            # Found a valid window
            #
            if offset == self.window_size:
                emg_window = cur_data["emg"][start_window:start_window + self.window_size]

                # Balance number of rest classes
                if (window_label == self.rest_label) and self.balance_classes:
                    if num_rest_samples > (num_samples / float(self.num_classes)):
                        start_window += self.overlap_size
                        continue
                    else:
                        num_rest_samples += 1
                num_samples += 1

                if obtain_all_samples:
                    win_repetition = cur_data["rerepetition"][start_window]
                    if not ((win_repetition == 2) or (win_repetition == 5)):
                        self.all_samples.append(emg_window)

                # Split into train/test:
                else:
                    win_feat = self.feature_extractor.extract_feature_point(emg_window)
                    win_repetition = cur_data["rerepetition"][start_window]

                    # Correct the window label
                    if window_label != self.rest_label:
                        if ex == self.E3_name:
                            window_label += self.E1_classes + self.E2_classes
                        elif ex == self.E2_name:
                            window_label += self.E1_classes

                    if (patient == "s8") or (patient == "s10"):
                        self.test_features.append(win_feat)
                        self.test_labels.append(window_label)
                    else:
                        self.train_features.append(win_feat)
                        self.train_labels.append(window_label)

                start_window += self.overlap_size

            else:
                start_window += offset

    def get_dataset_name(self):
        return "logical_v1"