import os.path
from collections import defaultdict
from dataclasses import dataclass
import random
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

from nltk.tokenize.treebank import TreebankWordTokenizer, TreebankWordDetokenizer

from benchmark.scenario import Instance
from common.general import ensure_file_downloaded, ensure_directory_exists, match_case
from .perturbation_description import PerturbationDescription
from .perturbation import Perturbation


@dataclass
class PersonNamePerturbation(Perturbation):
    """ Individual fairness perturbation for person names. """

    """ Short unique identifier of the perturbation (e.g., extra_space) """
    name: str = "person_name"

    """ Random seed """
    SEED = 1885

    """ Line seperator """
    LINE_SEP = "\n"

    """ Information needed to download person_names.txt """
    CODALAB_URI_TEMPLATE: str = "https://worksheets.codalab.org/rest/bundles/{bundle}/contents/blob/"
    CODALAB_BUNDLE: str = "0xa65e8f9a107c44f198eb4ad356bbda34"
    FILE_NAME: str = "person_names.txt"
    SOURCE_URI: str = CODALAB_URI_TEMPLATE.format(bundle=CODALAB_BUNDLE)
    OUTPUT_PATH = os.path.join("benchmark_output", "perturbations", name)

    """ Name types """
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    ANY = "any"

    """ Gender categories """
    GENDER_CATEGORY = "gender"
    FEMALE = "female"
    MALE = "male"
    NEUTRAL = "neutral"
    GENDERS = {FEMALE, MALE, NEUTRAL}

    @dataclass(frozen=True)
    class Description(PerturbationDescription):
        """ Description for the PersonNamePerturbation class. """

        name: str
        prob: float
        source_class: Tuple[Tuple[str, str], ...]
        target_class: Tuple[Tuple[str, str], ...]
        name_file_path: Optional[str]
        person_name_type: str
        preserve_gender: bool

    def __init__(
        self,
        prob: float,
        source_class: Dict[str, str],
        target_class: Dict[str, str],
        name_file_path: Optional[str] = None,
        person_name_type: str = FIRST_NAME,
        preserve_gender: bool = True,
    ):
        """ Initialize the person name perturbation.

        If name_file_path isn't provided, we use our default name mapping
        file, which can be found at:

            https://worksheets.codalab.org/rest/bundles/0xa65e8f9a107c44f198eb4ad356bbda34/contents/blob/

        The available categories in our default file and their values are:

            "race" => "white_american", "black_american",
                      "asian", "chinese", "hispanic", "russian", "white"

        The first names in our default file come from Caliskan et al. (2017),
        which derives its list from Greenwald (1998). The former removed some
        names from the latter because the corresponding tokens infrequently
        occured in Common Crawl, which was used as the training corpus for
        GloVe. We include the full list from the latter in our default file.

        The last names in our default file and their associated categories come
        from Garg et. al. (2017), which derives its list from
        Chalabi and Flowers (2014).

        Args:
            prob: Probability of substituting a word in the source class with
                a word in the target class given that a substitution is
                available.
            source_class: The properties of the source class. The keys of the
                dictionary should correspond to categories ("race", "gender",
                "religion, "age", etc.) and the values should be the
                corresponding values. If more than one category is provided,
                the source_names list will be constructed by finding the
                intersection of the names list for the provided categories.
            target_class: Same as source_class, but specifies the target_class.
            name_file_path: The absolute path to a file containing the
                category associations of names. Each row of the file must
                have the following format:

                    <name>,<name_type>[,<category>,<value>]*

                Here is a breakdown of the fields:
                    <name>: The name (e.g. Alex).
                    <name_type>: Must be one of "first_name" or "last_name".
                    <category>: The name of the category (e.g. Race, Gender,
                        Age, Religion, etc.)
                    <value>: Value of the preceding category.

                [,<category>,<value>]* denotes that any number of category
                    and value pairs can be appended to a line.

                Here are some example lines:
                    li,last_name,race,chinese
                    aiesha,first_name,race,black_american,gender,female

                Notes:
                    (1) For each field, the eading and trailing spaces are
                        ignored, but those in between words in a field are
                        kept.
                    (2) All the fields are lowered.
                    (3) It is possible for a name to have multiple associations
                        (e.g. with more than one age, gender etc.)

                We use the default file if None is provided.
            person_name_type: One of "first_name" or "last_name". If
                "last_name", preseverve_gender field must be False.
            preserve_gender: If set to True, we preserve the gender when
                mapping names of one category to those of another. If we can't
                find the gender association for a source_word, we randomly
                pick from one of the target names.
        """
        # TODO: This field should be inherited from the base perturbation class
        self.output_path: str = self.OUTPUT_PATH
        Path(self.output_path).mkdir(parents=True, exist_ok=True)

        # Random generator for our perturbation
        self.random: random.Random = random.Random(self.SEED)

        # Initialize the tokenizers
        self.tokenizer = TreebankWordTokenizer()
        self.detokenizer = TreebankWordDetokenizer()

        assert 0 <= prob <= 1
        self.prob = prob
        self.source_class: Dict[str, str] = source_class
        self.target_class: Dict[str, str] = target_class

        assert person_name_type in [self.FIRST_NAME, self.LAST_NAME]
        self.person_name_type = person_name_type

        self.name_file_path: Optional[str] = name_file_path
        if not self.name_file_path:
            self.name_file_path = self.download_name_file()

        # Get the possible source_names and target_names
        self.mapping_dict: Dict[str, Dict[str, Set[str]]] = self.load_name_file(self.name_file_path)
        assert self.mapping_dict
        self.source_names: Set[str] = self.get_possible_names(source_class)
        self.target_names: Set[str] = self.get_possible_names(target_class)

        self.preserve_gender: bool = preserve_gender
        if self.preserve_gender:
            assert self.person_name_type == self.FIRST_NAME
            assert self.GENDER_CATEGORY in self.mapping_dict and len(self.mapping_dict[self.GENDER_CATEGORY])

    @property
    def description(self) -> PerturbationDescription:
        """ Return a perturbation description for this class. """
        source_tuple = tuple([(k, v) for k, v in self.source_class.items()])
        target_tuple = tuple([(k, v) for k, v in self.target_class.items()])
        return PersonNamePerturbation.Description(
            self.name,
            self.prob,
            source_tuple,
            target_tuple,
            self.name_file_path,
            self.person_name_type,
            self.preserve_gender,
        )

    def get_possible_names(self, selected_class: Dict[str, str]) -> Set[str]:
        """ Return possible names given a selected class, using self.mapping_dict """
        selected_names = []
        for cat, val in selected_class.items():
            assert self.mapping_dict[cat][val]
            selected_names.append(self.mapping_dict[cat][val])
        return set.intersection(*selected_names)

    def download_name_file(self) -> str:
        """ Download the name file from CodaLab """
        data_path = os.path.join(self.output_path, "data")
        file_path: str = os.path.join(data_path, self.FILE_NAME)
        ensure_directory_exists(data_path)
        ensure_file_downloaded(source_url=self.SOURCE_URI, target_path=file_path)
        return file_path

    def load_name_file(self, file_path) -> Dict[str, Dict[str, Set[str]]]:
        """ Load the name file """
        mapping_dict: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
        delimiter = ","
        with open(file_path, encoding="utf-8") as f:
            for line in f.readlines():
                name, name_type, *categories = line.replace(self.LINE_SEP, "").split(delimiter)
                for ind in range(len(categories) // 2):
                    category_type, category = categories[2 * ind], categories[2 * ind + 1]
                    if self.person_name_type == name_type:
                        mapping_dict[category_type][category].add(name.strip().lower())
        return mapping_dict

    def get_name_gender(self, name: str) -> Optional[str]:
        """ Get the gender of the word and return one of FEMALE, MALE, and NEUTRAL. """
        gender_dict = self.mapping_dict[self.GENDER_CATEGORY]
        genders = (self.FEMALE, self.MALE, self.NEUTRAL)
        for gender in genders:
            if gender in gender_dict and name in gender_dict[gender]:
                return gender
        return None

    def process_word(
        self, word: str, subs_dict: Dict[str, str], nonsubs: Set[str]
    ) -> Tuple[str, Dict[str, str], Set[str]]:
        """ Process a word.

        Return the processed word, updated subs_dict and updated nonsubs. """
        gender_dict = self.mapping_dict[self.GENDER_CATEGORY]
        lowered_word = word.lower()
        if lowered_word in subs_dict:
            # If we already substituted the same word in the past, we substitute this word as well
            word = match_case(word, subs_dict[lowered_word])
        elif lowered_word not in nonsubs:
            # Only consider a word for substitution if we didn't pass on it before
            if lowered_word in self.source_names:
                if self.random.uniform(0, 1) < self.prob:
                    # Substitute the name
                    options = self.target_names
                    if self.preserve_gender:
                        name_gender = self.get_name_gender(lowered_word)
                        if name_gender:
                            options = self.target_names.intersection(gender_dict[name_gender])
                        # If we don't know the gender for the source names, we randomly pick one of the target names
                    word = match_case(word, self.random.choice(list(options)))
                    subs_dict[lowered_word] = word
                else:
                    # Do not substitute the name
                    nonsubs.add(lowered_word)
        return word, subs_dict, nonsubs

    def substitute_names(self, text: str) -> str:
        """ Substitute the source dialect in text with the target dialect. """
        subs_dict: Dict[str, str] = {}
        nonsubs: Set[str] = set()
        lines, new_lines = text.split(self.LINE_SEP), []
        for line in lines:
            words, new_words = self.tokenizer.tokenize(line), []
            for word in words:
                word, subs_dict, nonsubs = self.process_word(word, subs_dict, nonsubs)
                new_words.append(word)
            perturbed_line = str(self.detokenizer.detokenize(new_words))
            new_lines.append(perturbed_line)
        perturbed_text = self.LINE_SEP.join(new_lines)
        return perturbed_text

    def apply(self, instance: Instance, should_perturb_references: bool = True) -> Instance:
        """ Apply the perturbation to the provided instance. """
        assert instance.id is not None
        return super().apply(instance, should_perturb_references)

    def perturb(self, text: str) -> str:
        """ Perturb the provided text. """
        return self.substitute_names(text)
