"""Scene Understanding Based on Text Detection
Hila Manor & Adir Krayden

Find the geographical location of a given place in an urban area, based on the words that appear
in its pictures.
The algorithm is comprised of 3 step:
    1. Images received as input are processed to produce a unified panorama image.
    2. Text is extracted, processed and filtered from panorama.
        A distinction between the street signs and the rest of the signs is made.
    3. The separated information is used to search for the geographical location of the scene.


Images with good lighting conditions and enough words that characterize the location help.
Low image resolution limits the performance of the algorithm.
"""

# ~~~~~~~~~~~~~~~~~~~~~~~~~~ Imports ~~~~~~~~~~~~~~~~~~~~~~~
import argparse
import os
import cv2
import numpy as np
from panorama_maker import PanoramaMaker, DescriptorType, MatcherType
from image_windows import ImageWindows
from charnet_runner import CharNetRunner
from matplotlib import use
import box_algo
import text_algo
import google_query
use("TkAgg")
# ~~~~~~~~~~~~~~~~~~~~~~~~~~ Code ~~~~~~~~~~~~~~~~~~~~~~~~~~


def vis(img, instances):
    """ Visualise the extracted text by painting the text & bounding boxes on the picture

    :param img: image to draw upon the words. will not be changed.
    :param instances: WordInstances/BoxInstances to draw
    :return: copy of image with words drawn upon
    """
    img_word_ins = img.copy()
    for ins in instances:
        word_ins = ins.word if type(instances[0]) == box_algo.BoxInstance else ins
        word_bbox = word_ins.word_bbox
        cv2.polylines(img_word_ins, [word_bbox[:8].reshape((-1, 2)).astype(np.int32)],
                      True, (0, 255, 0), 2)
        cv2.putText(
            img_word_ins,
            '{}'.format(word_ins.text),
            (int(word_bbox[0]), int(word_bbox[1])), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1
        )
    return img_word_ins


def parse_dir(scene_path, output_path, char_net, dont_reorder):
    """ Runs the context analysis on the given images of the scene in the given directory

    :param scene_path: Directory containing images of the scene. images should overlap
    :param output_path: All of the algorithm output will be thrown out in this path
    :param char_net: charnetRunner instance to use to run extract the text
    :param dont_reorder: Boolean value to try and reorder the images, or treat them as ordered
    :return: None
    """
    panorama_gen = PanoramaMaker(descriptor_type=DescriptorType.SIFT, matcher_type=MatcherType.KNN)
    for im_name in sorted(os.listdir(scene_path)):
        print("[+] Working on \"%s\"..." % im_name)
        im_file = os.path.join(scene_path, im_name)
        im_original = cv2.imread(im_file)
        panorama_gen.add_photo(im_original)

    panorama = panorama_gen.create_panorama(dont_reorder)

    cv2.imwrite(os.path.join(output_path, 'panorama.png'), panorama)
    # panorama = cv2.imread(os.path.join(output_path, 'panorama.png'))

    windows = ImageWindows(panorama, input_size_cfg=1520)
    twords = []
    for idx, window in enumerate(windows, 1):
        print("[-] Splitting to windows: %d/%d" % (idx, len(windows)), end='\r')
        word_instances = char_net.get_absolute_window_words(windows, window)
        word_instances = char_net.clean_duplicate_words(word_instances)
        new_words_only = CharNetRunner.new_words_only(twords, word_instances)
        if new_words_only:
            twords += new_words_only
    print('\n[+] Done Extracting Text')
    vis_image = vis(panorama, twords)
    cv2.imwrite(os.path.join(output_path, 'all_text.png'), vis_image)

    with open(os.path.join(output_path, "words.pickle"), 'wb') as f:
        import pickle
        pickle.dump(twords, f)
        # twords = pickle.load(f)

    tboxes = box_algo.expand_word_data(twords, panorama)
    c_tboxes = text_algo.concat_words(tboxes, panorama)
    combined_vis_image = vis(panorama, c_tboxes)
    cv2.imwrite(os.path.join(output_path, 'combined_words.png'), combined_vis_image)

    streets, others = text_algo.analyze_extracted_words(c_tboxes)
    with open(os.path.join(output_path, "extracted_words.txt"), 'w') as f:
        f.write("streets:")
        f.writelines(['\n\t' + s.word.text for s in streets])
        f.write("\nothers:")
        f.writelines(['\n\t' + s.word.text for s in others])
        f.write('\n')
    google_query.search_location(streets, others, output_path)


if __name__ == '__main__':
    print("Gathering Data...")
    # ----- Creating Argument Parser -----
    parser = argparse.ArgumentParser(description="Main Runner")

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--scenes_dir", type=str,
                             help="path to multiple scenes parent directory")
    input_group.add_argument("--single_scene", type=str,
                             help="path to a directory containing one scene")
    parser.add_argument("--results_dir", type=str,
                        help="Results directory. "
                             "Default is to throw the output inside given input directory")
    parser.add_argument("--dont_reorder", action='store_true', help="Photos are with meaningful "
                                                                    "name, according to their "
                                                                    "order left to right")

    text_net_group = parser.add_argument_group('Text Recognition Network',
                                               'arguments related to the text '
                                               'detection and recognition network')
    text_net_group.add_argument("--config_file", help="path to config file", type=str,
                                default='.\\charnet\\config\\icdar2015_hourglass88.yaml')

    args = parser.parse_args()

    # while True:
    charnet = CharNetRunner(args.config_file)

    if args.results_dir:
        os.makedirs(args.results_dir, exist_ok=True)

    if args.scenes_dir:
        if not args.results_dir:
            args.results_dir = args.scenes_dir
        for scene in sorted(os.listdir(args.scenes_dir)):
            print("\nProcessing \"%s\":" % scene)
            curr_scene_path = os.path.join(args.scenes_dir, scene)
            curr_output_dir = os.path.join(args.results_dir, scene)
            os.makedirs(curr_output_dir, exist_ok=True)
            parse_dir(curr_scene_path, curr_output_dir, charnet, args.dont_reorder)
    else:
        if not args.results_dir:
            args.results_dir = args.single_scene
        parse_dir(args.single_scene, args.results_dir, charnet, args.dont_reorder)
