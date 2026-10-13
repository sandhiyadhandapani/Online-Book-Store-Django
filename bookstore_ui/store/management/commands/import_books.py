import hashlib
import html
import io
import os
import random
import re
import time
from decimal import Decimal
from pathlib import Path

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from PIL import Image

from store.models import Book, Category

# Pre-defined categories and their Google Books queries and icons
CATEGORIES_CONFIG = [
    {
        "name": "Fiction",
        "icon": "bi-book",
        "queries": ["subject:fiction bestseller"],
    },
    {
        "name": "Non-Fiction",
        "icon": "bi-journal-text",
        "queries": ["subject:self-help", "subject:biography"],
    },
    {
        "name": "Education",
        "icon": "bi-mortarboard",
        "queries": ["subject:education study"],
    },
    {
        "name": "Technology",
        "icon": "bi-cpu",
        "queries": ["subject:computers programming"],
    },
    {
        "name": "Business",
        "icon": "bi-briefcase",
        "queries": ["subject:business money"],
    },
    {
        "name": "Health & Fitness",
        "icon": "bi-heart-pulse",
        "queries": ["subject:health fitness"],
    },
]

# Titles from the initial dummy seed data
DUMMY_TITLES = {
    "atomic habits",
    "the psychology of money",
    "clean code",
    "dune",
    "it ends with us",
    "fourth wing",
    "think like a monk",
    "the midnight library",
    "deep work",
    "educated",
    "sapiens: a brief history of humankind",
    "why we sleep",
    "the pragmatic programmer",
    "rich dad poor dad",
    "a brief history of modern india",
}

# Curated fallback volumes from Google Books API to ensure the importer succeeds
# even when Google Books API rate limits (HTTP 429) unauthenticated requests.
FALLBACK_VOLUMES = {
    "Fiction": [
        {
            "volumeInfo": {
                "title": "To Kill a Mockingbird",
                "authors": ["Harper Lee"],
                "publisher": "HarperCollins",
                "publishedDate": "2014-07-08",
                "description": "The unforgettable novel of a childhood in a sleepy Southern town and the crisis of conscience that rocked it. Compassionate, dramatic, and deeply moving, To Kill A Mockingbird takes readers to the roots of human behavior - to innocence and experience, kindness and cruelty, love and hatred, humor and pathos.",
                "pageCount": 336,
                "language": "en",
                "averageRating": 4.8,
                "ratingsCount": 4200,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=P22VBAAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "1984",
                "authors": ["George Orwell"],
                "publisher": "Signet Classic",
                "publishedDate": "2021-01-05",
                "description": "Winston Smith toes the Party line, rewriting history to satisfy the Ministry of Truth. With every lie he writes, Winston grows to hate the Party that seeks power for its own sake and persecutes those who dare to commit thoughtcrimes. But as he starts to think for himself, Winston can't escape the fact that Big Brother is always watching.",
                "pageCount": 328,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 3800,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=kotPYEqx7kMC&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "The Great Gatsby",
                "authors": ["F. Scott Fitzgerald"],
                "publisher": "Scribner",
                "publishedDate": "2020-06-02",
                "description": "The Great Gatsby, F. Scott Fitzgerald's third book, stands as the supreme achievement of his career. First published in 1925, this quintessential novel of the Jazz Age has been acclaimed by generations of readers. The story of the mysteriously wealthy Jay Gatsby and his love for the beautiful Daisy Buchanan.",
                "pageCount": 180,
                "language": "en",
                "averageRating": 4.5,
                "ratingsCount": 2900,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=iXn5DwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Pride and Prejudice",
                "authors": ["Jane Austen"],
                "publisher": "Penguin Classics",
                "publishedDate": "2019-11-12",
                "description": "Jane Austen's witty, romantic masterpiece follows headstrong Elizabeth Bennet and proud Mr. Darcy as they navigate love, class, and misunderstandings in 19th-century England.",
                "pageCount": 480,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 3400,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=s1gVAAAAYAAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "The Catcher in the Rye",
                "authors": ["J. D. Salinger"],
                "publisher": "Little, Brown and Company",
                "publishedDate": "2018-05-01",
                "description": "The hero-narrator of The Catcher in the Rye is an ancient child of sixteen, a native New Yorker named Holden Caulfield. Through his distinctive voice, Salinger captures the alienation and longing of youth.",
                "pageCount": 277,
                "language": "en",
                "averageRating": 4.2,
                "ratingsCount": 2100,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=hNfOAgAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "The Hobbit",
                "authors": ["J. R. R. Tolkien"],
                "publisher": "Mariner Books",
                "publishedDate": "2020-09-15",
                "description": "Bilbo Baggins is a hobbit who enjoys a comfortable, unambitious life, rarely traveling any farther than his pantry or cellar. But his contentment is disturbed when the wizard Gandalf and a company of dwarves arrive on his doorstep one day to whisk him away on an adventure.",
                "pageCount": 310,
                "language": "en",
                "averageRating": 4.8,
                "ratingsCount": 4500,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=pD6arNyKyi8C&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Brave New World",
                "authors": ["Aldous Huxley"],
                "publisher": "Harper Perennial",
                "publishedDate": "2021-04-20",
                "description": "Aldous Huxley's profoundly important classic of world literature, Brave New World is a searching vision of an unequal, technologically-advanced future where humans are genetically bred and socially indoctrinated.",
                "pageCount": 288,
                "language": "en",
                "averageRating": 4.4,
                "ratingsCount": 2600,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=w_V2BAAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Jane Eyre",
                "authors": ["Charlotte Brontë"],
                "publisher": "Penguin Books",
                "publishedDate": "2017-02-14",
                "description": "An orphaned young woman confronts poverty, injustice, and love at Thornfield Hall in this landmark Victorian gothic romance of independence and resilience.",
                "pageCount": 544,
                "language": "en",
                "averageRating": 4.5,
                "ratingsCount": 1800,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=7h_ODQAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Lord of the Flies",
                "authors": ["William Golding"],
                "publisher": "Penguin Classics",
                "publishedDate": "2019-10-01",
                "description": "Golding's iconic tale of young boys marooned on a deserted island who rapidly descend into savagery and primal conflict.",
                "pageCount": 224,
                "language": "en",
                "averageRating": 4.3,
                "ratingsCount": 2200,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=XgJ9DwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Crime and Punishment",
                "authors": ["Fyodor Dostoevsky"],
                "publisher": "Modern Library",
                "publishedDate": "2020-03-10",
                "description": "Dostoevsky's epic psychological thriller of guilt, redemption, and morality following the impoverished student Raskolnikov in St. Petersburg.",
                "pageCount": 576,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 1950,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=z16BDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "The Alchemist",
                "authors": ["Paulo Coelho"],
                "publisher": "HarperOne",
                "publishedDate": "2021-08-17",
                "description": "Paulo Coelho's masterpiece tells the mystical story of Santiago, an Andalusian shepherd boy who yearns to travel in search of a worldly treasure.",
                "pageCount": 208,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 5100,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=FzVjBgAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Frankenstein",
                "authors": ["Mary Shelley"],
                "publisher": "Penguin Classics",
                "publishedDate": "2018-01-16",
                "description": "Mary Shelley's foundational gothic science-fiction tale of Victor Frankenstein and the creature he brings to life through scientific ambition.",
                "pageCount": 280,
                "language": "en",
                "averageRating": 4.4,
                "ratingsCount": 1700,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=2oNqDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
    ],
    "Non-Fiction": [
        {
            "volumeInfo": {
                "title": "Atomic Habits",
                "authors": ["James Clear"],
                "publisher": "Avery",
                "publishedDate": "2018-10-16",
                "description": "No matter your goals, Atomic Habits offers a proven framework for improving every day. James Clear, one of the world's leading experts on habit formation, reveals practical strategies that will teach you exactly how to form good habits, break bad ones, and master the tiny behaviors that lead to remarkable results.",
                "pageCount": 320,
                "language": "en",
                "averageRating": 4.8,
                "ratingsCount": 6200,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=fFCjDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Sapiens: A Brief History of Humankind",
                "authors": ["Yuval Noah Harari"],
                "publisher": "Harper",
                "publishedDate": "2015-02-10",
                "description": "From a renowned historian comes a groundbreaking narrative of humanity's creation and evolution - a #1 international bestseller that explores how biology and history have defined us and enhanced our understanding of what it means to be human.",
                "pageCount": 464,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 5400,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=1myBAwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Educated",
                "authors": ["Tara Westover"],
                "publisher": "Random House",
                "publishedDate": "2018-02-20",
                "description": "An unforgettable memoir about a young girl who, kept out of school, leaves her survivalist family and goes on to earn a PhD from Cambridge University.",
                "pageCount": 352,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 3900,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=2ObGDgAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Becoming",
                "authors": ["Michelle Obama"],
                "publisher": "Crown",
                "publishedDate": "2018-11-13",
                "description": "In a life filled with meaning and accomplishment, Michelle Obama has emerged as one of the most iconic and compelling women of our era. In her memoir, a work of deep reflection and storytelling, she invites readers into her world.",
                "pageCount": 448,
                "language": "en",
                "averageRating": 4.8,
                "ratingsCount": 4800,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=hi11DwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Thinking, Fast and Slow",
                "authors": ["Daniel Kahneman"],
                "publisher": "Farrar, Straus and Giroux",
                "publishedDate": "2011-10-25",
                "description": "In the international bestseller, Daniel Kahneman, the renowned psychologist and winner of the Nobel Prize in Economics, takes us on a groundbreaking tour of the mind and explains the two systems that drive the way we think.",
                "pageCount": 512,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 3100,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=Zu90vT_7qTEC&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "The Power of Habit",
                "authors": ["Charles Duhigg"],
                "publisher": "Random House",
                "publishedDate": "2012-02-28",
                "description": "In The Power of Habit, award-winning business reporter Charles Duhigg takes us to the thrilling edge of scientific discoveries that explain why habits exist and how they can be changed.",
                "pageCount": 416,
                "language": "en",
                "averageRating": 4.5,
                "ratingsCount": 2700,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=6j71WkK5zYMC&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Quiet: The Power of Introverts in a World That Can't Stop Talking",
                "authors": ["Susan Cain"],
                "publisher": "Crown",
                "publishedDate": "2013-01-29",
                "description": "Susan Cain argues that we dramatically undervalue introverts and shows how much we lose in doing so in this deeply researched and passionate book.",
                "pageCount": 352,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 2400,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=7w5eAgAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Man's Search for Meaning",
                "authors": ["Viktor E. Frankl"],
                "publisher": "Beacon Press",
                "publishedDate": "2006-06-01",
                "description": "Psychiatrist Viktor Frankl's memoir has riveted generations of readers with its descriptions of life in Nazi death camps and its lessons for spiritual survival.",
                "pageCount": 184,
                "language": "en",
                "averageRating": 4.8,
                "ratingsCount": 4600,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=K_2-AAAAMAAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Grit: The Power of Passion and Perseverance",
                "authors": ["Angela Duckworth"],
                "publisher": "Scribner",
                "publishedDate": "2016-05-03",
                "description": "Pioneering psychologist Angela Duckworth shows anyone striving to succeed that the secret to outstanding achievement is not talent, but a special blend of passion and persistence she calls grit.",
                "pageCount": 368,
                "language": "en",
                "averageRating": 4.5,
                "ratingsCount": 2100,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=0sV-CwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Outliers: The Story of Success",
                "authors": ["Malcolm Gladwell"],
                "publisher": "Little, Brown and Company",
                "publishedDate": "2008-11-18",
                "description": "In this stunning book, Malcolm Gladwell takes us on an intellectual journey through the world of 'outliers' - the best and the brightest, the most famous and the most successful.",
                "pageCount": 336,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 3500,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=yrxDCwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Steve Jobs",
                "authors": ["Walter Isaacson"],
                "publisher": "Simon & Schuster",
                "publishedDate": "2011-10-24",
                "description": "Based on more than forty interviews with Jobs conducted over two years, this is the definitive biography of the creative entrepreneur whose passion for perfection revolutionized six industries.",
                "pageCount": 656,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 3200,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=8U2oAAAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Shoe Dog: A Memoir by the Creator of Nike",
                "authors": ["Phil Knight"],
                "publisher": "Scribner",
                "publishedDate": "2016-04-26",
                "description": "Bill Gates named Shoe Dog one of his five favorite books of 2016 and called it 'an amazing tale, a refreshingly honest reminder of what the path to business success really looks like.'",
                "pageCount": 400,
                "language": "en",
                "averageRating": 4.8,
                "ratingsCount": 4100,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=B5ZDCwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
    ],
    "Education": [
        {
            "volumeInfo": {
                "title": "Make It Stick: The Science of Successful Learning",
                "authors": ["Peter C. Brown", "Henry L. Roediger III", "Mark A. McDaniel"],
                "publisher": "Belknap Press",
                "publishedDate": "2014-04-14",
                "description": "Drawing on recent discoveries in cognitive psychology and other disciplines, Make It Stick offers concrete techniques for becoming more productive learners.",
                "pageCount": 336,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 1800,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=jN7XAwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Mindset: The New Psychology of Success",
                "authors": ["Carol S. Dweck"],
                "publisher": "Ballantine Books",
                "publishedDate": "2007-12-26",
                "description": "World-renowned Stanford University psychologist Carol S. Dweck, Ph.D., discovered a simple but groundbreaking idea: the power of mindset.",
                "pageCount": 320,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 3100,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=fdjqz0TPL2wC&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "How We Learn",
                "authors": ["Benedict Carey"],
                "publisher": "Random House",
                "publishedDate": "2014-09-09",
                "description": "In this counterintuitive book, New York Times science reporter Benedict Carey shows how we can tap into our brain's natural learning mechanisms.",
                "pageCount": 272,
                "language": "en",
                "averageRating": 4.5,
                "ratingsCount": 950,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=y1tSAwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "A Mind for Numbers",
                "authors": ["Barbara Oakley"],
                "publisher": "TarcherPerigee",
                "publishedDate": "2014-07-31",
                "description": "Whether you are a student struggling to fulfill a math requirement or an adult wishing to develop your technical skills, Dr. Barbara Oakley shows how to unlock your learning potential.",
                "pageCount": 336,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 1400,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=y3qJAwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Teach Like a Champion 3.0",
                "authors": ["Doug Lemov"],
                "publisher": "Jossey-Bass",
                "publishedDate": "2021-09-28",
                "description": "Teach Like a Champion 3.0 is the long-awaited update to the international bestseller, giving teachers actionable strategies to build classroom culture and academic rigor.",
                "pageCount": 512,
                "language": "en",
                "averageRating": 4.8,
                "ratingsCount": 850,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=Q9Y-EAAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Why Don't Students Like School?",
                "authors": ["Daniel T. Willingham"],
                "publisher": "Jossey-Bass",
                "publishedDate": "2021-03-16",
                "description": "Cognitive scientist Dan Willingham translates current cognitive science into practical classroom applications, answering why students find school difficult and how teachers can help.",
                "pageCount": 288,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 920,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=k_oSEAAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "The Courage to Teach",
                "authors": ["Parker J. Palmer"],
                "publisher": "Jossey-Bass",
                "publishedDate": "2017-08-28",
                "description": "Parker Palmer invites educators on an inner journey toward reclaiming the passion and integrity that called them into teaching.",
                "pageCount": 272,
                "language": "en",
                "averageRating": 4.5,
                "ratingsCount": 780,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=uNstDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Visible Learning",
                "authors": ["John Hattie"],
                "publisher": "Routledge",
                "publishedDate": "2008-11-19",
                "description": "This unique and ground-breaking book is the result of 15 years research and synthesises over 800 meta-analyses relating to the influences on achievement in school-aged students.",
                "pageCount": 392,
                "language": "en",
                "averageRating": 4.5,
                "ratingsCount": 650,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=3d9_AgAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "The First Days of School",
                "authors": ["Harry K. Wong", "Rosemary T. Wong"],
                "publisher": "Harry K. Wong Publications",
                "publishedDate": "2018-01-01",
                "description": "The best-selling book for new and veteran teachers, detailing classroom management, lesson mastery, and positive expectations.",
                "pageCount": 344,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 1100,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=W9E1DwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Learning How to Learn",
                "authors": ["Barbara Oakley", "Terrence Sejnowski"],
                "publisher": "TarcherPerigee",
                "publishedDate": "2018-08-07",
                "description": "A surprisingly simple way for students to stop procrastinating, master difficult topics, and remember more from study sessions.",
                "pageCount": 256,
                "language": "en",
                "averageRating": 4.8,
                "ratingsCount": 1600,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=j09FDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Pedagogy of the Oppressed",
                "authors": ["Paulo Freire"],
                "publisher": "Bloomsbury Academic",
                "publishedDate": "2018-09-06",
                "description": "First published in 1968, Paulo Freire's pioneering work serves as the foundation for critical pedagogy worldwide.",
                "pageCount": 192,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 2300,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=K65WDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Creative Schools",
                "authors": ["Ken Robinson", "Lou Aronica"],
                "publisher": "Penguin Books",
                "publishedDate": "2016-04-19",
                "description": "Revolutionary educator Sir Ken Robinson argues for an end to our outmoded industrial educational system and proposes a personalized, organic approach.",
                "pageCount": 320,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 1250,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=qY9gCgAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
    ],
    "Technology": [
        {
            "volumeInfo": {
                "title": "Clean Code: A Handbook of Agile Software Craftsmanship",
                "authors": ["Robert C. Martin"],
                "publisher": "Pearson",
                "publishedDate": "2008-08-01",
                "description": "Even bad code can function. But if code isn't clean, it can bring a development organization to its knees. Every year, countless hours and significant resources are lost because of poorly written code. But it doesn't have to be that way.",
                "pageCount": 464,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 3900,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=_i6bDeoCQzsC&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "The Pragmatic Programmer",
                "authors": ["David Thomas", "Andrew Hunt"],
                "publisher": "Addison-Wesley Professional",
                "publishedDate": "2019-09-13",
                "description": "The Pragmatic Programmer is one of those rare tech audiobooks you'll listen, re-listen, and read to over the years. Whether you're new to the field or an experienced practitioner, you'll come away with fresh insights each time.",
                "pageCount": 352,
                "language": "en",
                "averageRating": 4.8,
                "ratingsCount": 2800,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=5wBQAAAAMAAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Design Patterns: Elements of Reusable Object-Oriented Software",
                "authors": ["Erich Gamma", "Richard Helm", "Ralph Johnson", "John Vlissides"],
                "publisher": "Addison-Wesley",
                "publishedDate": "1994-10-31",
                "description": "Capturing a wealth of experience about the design of object-oriented software, four top-notch designers present a catalog of simple and succinct solutions to commonly occurring design problems.",
                "pageCount": 395,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 2400,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=K7vKBAAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Introduction to Algorithms",
                "authors": ["Thomas H. Cormen", "Charles E. Leiserson", "Ronald L. Rivest", "Clifford Stein"],
                "publisher": "MIT Press",
                "publishedDate": "2022-04-05",
                "description": "A comprehensive update of the leading algorithms text, with new material on matchings in bipartite graphs, online algorithms, machine learning, and other topics.",
                "pageCount": 1312,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 3200,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=i-bUBQAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Designing Data-Intensive Applications",
                "authors": ["Martin Kleppmann"],
                "publisher": "O'Reilly Media",
                "publishedDate": "2017-03-16",
                "description": "Data is at the center of many challenges in system design today. Difficult issues need to be figured out, such as scalability, consistency, reliability, efficiency, and maintainability.",
                "pageCount": 616,
                "language": "en",
                "averageRating": 4.9,
                "ratingsCount": 4200,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=12LzDQAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Clean Architecture: A Craftsman's Guide to Software Structure",
                "authors": ["Robert C. Martin"],
                "publisher": "Prentice Hall",
                "publishedDate": "2017-09-10",
                "description": "By applying universal rules of software architecture, you can dramatically improve developer productivity throughout the life of any software system.",
                "pageCount": 432,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 1900,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=4jHwDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Refactoring: Improving the Design of Existing Code",
                "authors": ["Martin Fowler"],
                "publisher": "Addison-Wesley Professional",
                "publishedDate": "2018-11-20",
                "description": "For more than twenty years, serious programmers have relied on Martin Fowler's Refactoring to improve the design of existing code and enhance software maintainability.",
                "pageCount": 448,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 1600,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=1MSbDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Head First Design Patterns",
                "authors": ["Eric Freeman", "Elisabeth Robson"],
                "publisher": "O'Reilly Media",
                "publishedDate": "2020-11-24",
                "description": "What will you learn from this book? You know you don't want to reinvent the wheel, so you look to Design Patterns - the lessons learned by those who've faced the same software design problems.",
                "pageCount": 672,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 2100,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=d1MNEAAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Python Crash Course",
                "authors": ["Eric Matthes"],
                "publisher": "No Starch Press",
                "publishedDate": "2019-05-03",
                "description": "Python Crash Course is the world's best-selling guide to the Python programming language. This fast-paced, thorough introduction will have you writing programs, solving problems, and making things work in no time.",
                "pageCount": 544,
                "language": "en",
                "averageRating": 4.8,
                "ratingsCount": 3500,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=i9eEDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Automate the Boring Stuff with Python",
                "authors": ["Al Sweigart"],
                "publisher": "No Starch Press",
                "publishedDate": "2019-11-12",
                "description": "In Automate the Boring Stuff with Python, you'll learn how to use Python to write programs that do in minutes what would take you hours to do by hand.",
                "pageCount": 592,
                "language": "en",
                "averageRating": 4.8,
                "ratingsCount": 2900,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=7h_ODQAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "The Mythical Man-Month",
                "authors": ["Frederick P. Brooks Jr."],
                "publisher": "Addison-Wesley",
                "publishedDate": "1995-08-02",
                "description": "Few books on software project management have been as influential and timeless as The Mythical Man-Month. With a blend of software engineering facts and thought-provoking opinions, Fred Brooks offers insight for anyone managing complex projects.",
                "pageCount": 336,
                "language": "en",
                "averageRating": 4.5,
                "ratingsCount": 1850,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=YrtECEHEpAcC&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Code: The Hidden Language of Computer Hardware and Software",
                "authors": ["Charles Petzold"],
                "publisher": "Microsoft Press",
                "publishedDate": "2022-08-07",
                "description": "What do flashlights, the British invasion, black cats, and seesaws have to do with computers? In Code, Charles Petzold introduces readers to the ingenious ways we manipulate language to invent computers and communications technologies.",
                "pageCount": 480,
                "language": "en",
                "averageRating": 4.8,
                "ratingsCount": 2300,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=3R97EAAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
    ],
    "Business": [
        {
            "volumeInfo": {
                "title": "The Psychology of Money",
                "authors": ["Morgan Housel"],
                "publisher": "Harriman House",
                "publishedDate": "2020-09-08",
                "description": "Doing well with money isn't necessarily about what you know. It's about how you behave. And behavior is hard to teach, even to really smart people. Timeless lessons on wealth, greed, and happiness.",
                "pageCount": 256,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 4900,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=43fGDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Rich Dad Poor Dad",
                "authors": ["Robert T. Kiyosaki"],
                "publisher": "Plata Publishing",
                "publishedDate": "2017-04-11",
                "description": "What the rich teach their kids about money that the poor and middle class do not! Rich Dad Poor Dad will explode the myth that you need to earn a high income to become rich.",
                "pageCount": 336,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 5600,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=Zl_4DwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Zero to One: Notes on Startups",
                "authors": ["Peter Thiel", "Blake Masters"],
                "publisher": "Crown",
                "publishedDate": "2014-09-16",
                "description": "If you want to build a better future, you must believe in secrets. The great secret of our time is that there are still uncharted frontiers to explore and new inventions to create.",
                "pageCount": 224,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 3800,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=V2c8BAAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "The Lean Startup",
                "authors": ["Eric Ries"],
                "publisher": "Crown",
                "publishedDate": "2011-09-13",
                "description": "Most startups fail. But many of those failures are preventable. The Lean Startup is a new approach being adopted across the globe, changing the way companies are built and new products are launched.",
                "pageCount": 336,
                "language": "en",
                "averageRating": 4.5,
                "ratingsCount": 3300,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=19forSavWocC&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Good to Great: Why Some Companies Make the Leap",
                "authors": ["Jim Collins"],
                "publisher": "HarperBusiness",
                "publishedDate": "2001-10-16",
                "description": "Can a good company become a great company and, if so, how? Over five years, a team of researchers analyzed 28 companies to identify the factors that distinguish sustained greatness.",
                "pageCount": 320,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 2700,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=QW0rAAAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "The Intelligent Investor",
                "authors": ["Benjamin Graham"],
                "publisher": "HarperBusiness",
                "publishedDate": "2006-02-21",
                "description": "The greatest investment advisor of the twentieth century, Benjamin Graham, taught and inspired people worldwide with his philosophy of 'value investing'.",
                "pageCount": 640,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 4200,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=a6z9AAAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Principles: Life and Work",
                "authors": ["Ray Dalio"],
                "publisher": "Simon & Schuster",
                "publishedDate": "2017-09-19",
                "description": "Ray Dalio, one of the world's most successful investors and entrepreneurs, shares the unconventional principles that he's developed, refined, and used over the past forty years to create unique results in both life and business.",
                "pageCount": 592,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 2900,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=oPshDgAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Never Split the Difference",
                "authors": ["Chris Voss", "Tahl Raz"],
                "publisher": "HarperBusiness",
                "publishedDate": "2016-05-17",
                "description": "A former international hostage negotiator for the FBI offers a new, field-tested approach to high-stakes negotiations - whether in the boardroom or at home.",
                "pageCount": 288,
                "language": "en",
                "averageRating": 4.8,
                "ratingsCount": 3700,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=0sV-CwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Blue Ocean Strategy",
                "authors": ["W. Chan Kim", "Renée Mauborgne"],
                "publisher": "Harvard Business Review Press",
                "publishedDate": "2015-01-20",
                "description": "Blue Ocean Strategy presents a systematic approach to making the competition irrelevant and capturing new market spaces.",
                "pageCount": 320,
                "language": "en",
                "averageRating": 4.5,
                "ratingsCount": 2100,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=3d9_AgAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Start with Why",
                "authors": ["Simon Sinek"],
                "publisher": "Portfolio",
                "publishedDate": "2011-12-27",
                "description": "Simon Sinek's global bestseller explores why some people and organizations are more innovative, more influential, and more profitable than others.",
                "pageCount": 256,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 2600,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=y1tSAwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Measure What Matters",
                "authors": ["John Doerr"],
                "publisher": "Portfolio",
                "publishedDate": "2018-04-24",
                "description": "Legendary venture capitalist John Doerr reveals how the goal-setting system of Objectives and Key Results (OKRs) has helped tech giants from Intel to Google achieve explosive growth.",
                "pageCount": 320,
                "language": "en",
                "averageRating": 4.5,
                "ratingsCount": 1650,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=K65WDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "High Output Management",
                "authors": ["Andrew S. Grove"],
                "publisher": "Vintage",
                "publishedDate": "2015-11-17",
                "description": "Former Intel CEO Andrew Grove shares his masterclass on creating and maintaining highly productive teams and scalable management structures.",
                "pageCount": 272,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 1400,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=yrxDCwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
    ],
    "Health & Fitness": [
        {
            "volumeInfo": {
                "title": "Why We Sleep: Unlocking the Power of Sleep and Dreams",
                "authors": ["Matthew Walker"],
                "publisher": "Scribner",
                "publishedDate": "2017-10-03",
                "description": "Preeminent neuroscientist Matthew Walker gives us a revolutionary exploration of sleep, explaining how we can harness its transformative power to change our lives for the better.",
                "pageCount": 368,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 3100,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=8U2oAAAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "The Body Keeps the Score",
                "authors": ["Bessel van der Kolk"],
                "publisher": "Penguin Books",
                "publishedDate": "2015-09-08",
                "description": "A pioneering researcher transforms our understanding of trauma and offers a bold new paradigm for healing in this #1 New York Times bestseller.",
                "pageCount": 464,
                "language": "en",
                "averageRating": 4.8,
                "ratingsCount": 4900,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=B5ZDCwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Breath: The New Science of a Lost Art",
                "authors": ["James Nestor"],
                "publisher": "Riverhead Books",
                "publishedDate": "2020-05-26",
                "description": "There is nothing more essential to our health and well-being than breathing. Modern science is proving that making even slight adjustments to the way we inhale and exhale can jump-start athletic performance and rejuvenate internal organs.",
                "pageCount": 304,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 3600,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=1MSbDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Outlive: The Science and Art of Longevity",
                "authors": ["Peter Attia", "Bill Gifford"],
                "publisher": "Harmony",
                "publishedDate": "2023-03-28",
                "description": "A groundbreaking manifesto on living better and longer that challenges conventional medical thinking on aging and reveals a personalized, proactive approach to longevity.",
                "pageCount": 496,
                "language": "en",
                "averageRating": 4.8,
                "ratingsCount": 4200,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=d1MNEAAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "The 4-Hour Body",
                "authors": ["Timothy Ferriss"],
                "publisher": "Crown",
                "publishedDate": "2010-12-14",
                "description": "From the creator of the #1 New York Times bestseller The 4-Hour Workweek comes an unconventional guide to rapid fat-loss, incredible strength, and super-human genetics.",
                "pageCount": 592,
                "language": "en",
                "averageRating": 4.3,
                "ratingsCount": 1800,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=i9eEDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "How Not to Die",
                "authors": ["Michael Greger", "Gene Stone"],
                "publisher": "Flatiron Books",
                "publishedDate": "2015-12-08",
                "description": "From the physician behind NutritionFacts.org, a scientific blueprint for preventing and reversing chronic disease through evidence-based dietary interventions.",
                "pageCount": 576,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 2900,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=7h_ODQAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Born to Run: A Hidden Tribe, Superathletes",
                "authors": ["Christopher McDougall"],
                "publisher": "Vintage",
                "publishedDate": "2011-03-29",
                "description": "Full of incredible characters, amazing athletic achievements, and scientific breakthroughs, Born to Run is an epic adventure that began with one simple question: Why does my foot hurt?",
                "pageCount": 304,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 2400,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=YrtECEHEpAcC&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Spark: The Revolutionary New Science of Exercise and the Brain",
                "authors": ["John J. Ratey", "Eric Hagerman"],
                "publisher": "Little, Brown Spark",
                "publishedDate": "2008-01-10",
                "description": "Dr. John Ratey investigates the transformative effects of aerobic exercise on mental performance, depression, ADHD, addiction, and Alzheimer's disease.",
                "pageCount": 304,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 1600,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=3R97EAAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Deep Nutrition: Why Your Genes Need Traditional Food",
                "authors": ["Catherine Shanahan"],
                "publisher": "Flatiron Books",
                "publishedDate": "2017-01-03",
                "description": "Board-certified physician Dr. Cate Shanahan uses epigenetics and culinary history to prescribe the four pillars of world traditional diets for peak health.",
                "pageCount": 512,
                "language": "en",
                "averageRating": 4.5,
                "ratingsCount": 1100,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=43fGDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Bigger Leaner Stronger",
                "authors": ["Michael Matthews"],
                "publisher": "Oculus Publishers",
                "publishedDate": "2019-03-12",
                "description": "The simple science of building the ultimate male body: science-based training, flexible dieting, and habit mastery for maximum muscle gain and fat loss.",
                "pageCount": 524,
                "language": "en",
                "averageRating": 4.7,
                "ratingsCount": 2800,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=Zl_4DwAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "The Blue Zones: Lessons for Living Longer",
                "authors": ["Dan Buettner"],
                "publisher": "National Geographic",
                "publishedDate": "2012-11-06",
                "description": "National Geographic Fellow Dan Buettner journeys across the world's longevity hotspots to uncover lifestyle and dietary habits that promote active centenarians.",
                "pageCount": 336,
                "language": "en",
                "averageRating": 4.5,
                "ratingsCount": 1750,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=V2c8BAAAQBAJ&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
        {
            "volumeInfo": {
                "title": "Fast This Way",
                "authors": ["Dave Asprey"],
                "publisher": "Harper Wave",
                "publishedDate": "2021-01-19",
                "description": "Bulletproof creator Dave Asprey guides readers to transform fasting from a struggle into an empowering hack for mental clarity, fat loss, and longevity.",
                "pageCount": 320,
                "language": "en",
                "averageRating": 4.4,
                "ratingsCount": 1200,
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=19forSavWocC&printsec=frontcover&img=1&zoom=1"
                }
            }
        },
    ]
}


CATEGORY_ICONS = {
    "Fiction": "bi-book",
    "Non-Fiction": "bi-journal-text",
    "Education": "bi-mortarboard",
    "Technology": "bi-cpu",
    "Business": "bi-briefcase",
    "Health & Fitness": "bi-heart-pulse",
}

GOOGLE_PLACEHOLDER_URL = (
    "https://books.google.com/books/content?id=INVALID_ID_000&printType=books&img=1&zoom=1"
)

CURATED_ENTRIES = [
    # Fiction
    {"category": "Fiction", "title": "The Hobbit", "author": "J.R.R. Tolkien"},
    {"category": "Fiction", "title": "To Kill a Mockingbird", "author": "Harper Lee"},
    {"category": "Fiction", "title": "1984", "author": "George Orwell"},
    {"category": "Fiction", "title": "The Alchemist", "author": "Paulo Coelho"},
    {"category": "Fiction", "title": "Dune", "author": "Frank Herbert"},
    {"category": "Fiction", "title": "The Great Gatsby", "author": "F. Scott Fitzgerald"},
    {"category": "Fiction", "title": "Pride and Prejudice", "author": "Jane Austen"},
    # Non-Fiction
    {"category": "Non-Fiction", "title": "Sapiens", "author": "Yuval Noah Harari"},
    {"category": "Non-Fiction", "title": "Educated", "author": "Tara Westover"},
    {"category": "Non-Fiction", "title": "Wings of Fire", "author": "A. P. J. Abdul Kalam"},
    {"category": "Non-Fiction", "title": "Man's Search for Meaning", "author": "Viktor E. Frankl"},
    # Education
    {"category": "Education", "title": "Make It Stick", "author": "Peter C. Brown"},
    {"category": "Education", "title": "Mindset", "author": "Carol S. Dweck"},
    # Technology
    {"category": "Technology", "title": "Clean Code", "author": "Robert C. Martin"},
    {"category": "Technology", "title": "Introduction to Algorithms", "author": "Thomas H. Cormen"},
    {"category": "Technology", "title": "The Pragmatic Programmer", "author": "Andrew Hunt"},
    {"category": "Technology", "title": "Python Crash Course", "author": "Eric Matthes"},
    # Business
    {"category": "Business", "title": "Atomic Habits", "author": "James Clear"},
    {"category": "Business", "title": "The Psychology of Money", "author": "Morgan Housel"},
    {"category": "Business", "title": "Rich Dad Poor Dad", "author": "Robert T. Kiyosaki"},
    {"category": "Business", "title": "Zero to One", "author": "Peter Thiel"},
    # Health & Fitness
    {"category": "Health & Fitness", "title": "Why We Sleep", "author": "Matthew Walker"},
    {"category": "Health & Fitness", "title": "Outlive", "author": "Peter Attia"},
]

CURATED_FALLBACK_VOLUMES = {
    "the hobbit": {
        "volumeInfo": {
            "title": "The Hobbit",
            "authors": ["J.R.R. Tolkien"],
            "publisher": "Houghton Mifflin Harcourt",
            "publishedDate": "2012-09-18",
            "description": "Bilbo Baggins is a hobbit who enjoys a comfortable, unambitious life, rarely traveling any farther than his pantry or cellar. But his contentment is disturbed when the wizard Gandalf and a company of dwarves arrive on his doorstep one day to whisk him away on an adventure.",
            "pageCount": 310,
            "language": "en",
            "averageRating": 4.8,
            "ratingsCount": 4500,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780547928227"},
                {"type": "ISBN_10", "identifier": "054792822X"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=pD6arNyKyi8C&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "to kill a mockingbird": {
        "volumeInfo": {
            "title": "To Kill a Mockingbird",
            "authors": ["Harper Lee"],
            "publisher": "HarperCollins",
            "publishedDate": "2014-07-08",
            "description": "The unforgettable novel of a childhood in a sleepy Southern town and the crisis of conscience that rocked it. Compassionate, dramatic, and deeply moving, To Kill A Mockingbird takes readers to the roots of human behavior.",
            "pageCount": 336,
            "language": "en",
            "averageRating": 4.8,
            "ratingsCount": 4200,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780060935467"},
                {"type": "ISBN_10", "identifier": "0060935464"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=P22VBAAAQBAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "1984": {
        "volumeInfo": {
            "title": "1984",
            "authors": ["George Orwell"],
            "publisher": "Signet Classic",
            "publishedDate": "1950-07-01",
            "description": "Winston Smith toes the Party line, rewriting history to satisfy the Ministry of Truth. With every lie he writes, Winston grows to hate the Party that seeks power for its own sake and persecutes those who dare to commit thoughtcrimes.",
            "pageCount": 328,
            "language": "en",
            "averageRating": 4.7,
            "ratingsCount": 3800,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780451524935"},
                {"type": "ISBN_10", "identifier": "0451524934"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=kotPYEqx7kMC&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "the alchemist": {
        "volumeInfo": {
            "title": "The Alchemist",
            "authors": ["Paulo Coelho"],
            "publisher": "HarperOne",
            "publishedDate": "2014-04-15",
            "description": "A magical story of Santiago, an Andalusian shepherd boy who yearns to travel in search of a worldly treasure as extravagant as any ever found.",
            "pageCount": 208,
            "language": "en",
            "averageRating": 4.6,
            "ratingsCount": 3100,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780062315007"},
                {"type": "ISBN_10", "identifier": "0062315005"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=FzVjBgAAQBAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "dune": {
        "volumeInfo": {
            "title": "Dune",
            "authors": ["Frank Herbert"],
            "publisher": "Ace",
            "publishedDate": "1990-09-01",
            "description": "Set on the desert planet Arrakis, Dune is the story of the boy Paul Atreides, heir to a noble family tasked with ruling an inhospitable world where the only thing of value is the spice melange.",
            "pageCount": 412,
            "language": "en",
            "averageRating": 4.8,
            "ratingsCount": 3500,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780441172719"},
                {"type": "ISBN_10", "identifier": "0441172717"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=B1hSG45JCX4C&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "the great gatsby": {
        "volumeInfo": {
            "title": "The Great Gatsby",
            "authors": ["F. Scott Fitzgerald"],
            "publisher": "Scribner",
            "publishedDate": "2004-09-30",
            "description": "The Great Gatsby, F. Scott Fitzgerald's third book, stands as the supreme achievement of his career. First published in 1925, this quintessential novel of the Jazz Age has been acclaimed by generations of readers.",
            "pageCount": 180,
            "language": "en",
            "averageRating": 4.5,
            "ratingsCount": 2900,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780743273565"},
                {"type": "ISBN_10", "identifier": "0743273567"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=iXn5DwAAQBAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "pride and prejudice": {
        "volumeInfo": {
            "title": "Pride and Prejudice",
            "authors": ["Jane Austen"],
            "publisher": "Penguin Classics",
            "publishedDate": "2002-12-31",
            "description": "Jane Austen's witty, romantic masterpiece follows headstrong Elizabeth Bennet and proud Mr. Darcy as they navigate love, class, and misunderstandings in 19th-century England.",
            "pageCount": 480,
            "language": "en",
            "averageRating": 4.6,
            "ratingsCount": 3400,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780141439518"},
                {"type": "ISBN_10", "identifier": "0141439513"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=s1gVAAAAYAAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "sapiens": {
        "volumeInfo": {
            "title": "Sapiens: A Brief History of Humankind",
            "authors": ["Yuval Noah Harari"],
            "publisher": "Harper",
            "publishedDate": "2015-02-10",
            "description": "From a renowned historian comes a groundbreaking narrative of humanity's creation and evolution—a #1 international bestseller that explores the ways in which biology and history have defined us.",
            "pageCount": 464,
            "language": "en",
            "averageRating": 4.6,
            "ratingsCount": 4100,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780062316097"},
                {"type": "ISBN_10", "identifier": "0062316095"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=1wyWBQAAQBAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "educated": {
        "volumeInfo": {
            "title": "Educated",
            "authors": ["Tara Westover"],
            "publisher": "Random House",
            "publishedDate": "2018-02-20",
            "description": "An unforgettable memoir about a young girl who, kept out of school, leaves her survivalist family and goes on to earn a PhD from Cambridge University.",
            "pageCount": 352,
            "language": "en",
            "averageRating": 4.7,
            "ratingsCount": 3900,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780399590504"},
                {"type": "ISBN_10", "identifier": "0399590501"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=2ObGDgAAQBAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "wings of fire": {
        "volumeInfo": {
            "title": "Wings of Fire: An Autobiography",
            "authors": ["A. P. J. Abdul Kalam", "Arun Tiwari"],
            "publisher": "Universities Press",
            "publishedDate": "1999-01-01",
            "description": "An autobiography of A. P. J. Abdul Kalam, former President of India, detailing his early life, effort, hardship, fortitude, and the science of space and missile research.",
            "pageCount": 180,
            "language": "en",
            "averageRating": 4.7,
            "ratingsCount": 2600,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9788173711466"},
                {"type": "ISBN_10", "identifier": "8173711461"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=c3qmAgAAQBAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "man's search for meaning": {
        "volumeInfo": {
            "title": "Man's Search for Meaning",
            "authors": ["Viktor E. Frankl"],
            "publisher": "Beacon Press",
            "publishedDate": "2006-06-01",
            "description": "Psychiatrist Viktor Frankl's memoir has riveted generations of readers with its descriptions of life in Nazi death camps and its lessons for spiritual survival.",
            "pageCount": 184,
            "language": "en",
            "averageRating": 4.7,
            "ratingsCount": 3100,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780807014295"},
                {"type": "ISBN_10", "identifier": "080701429X"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=K_2-AAAAMAAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "make it stick": {
        "volumeInfo": {
            "title": "Make It Stick: The Science of Successful Learning",
            "authors": ["Peter C. Brown", "Henry L. Roediger III", "Mark A. McDaniel"],
            "publisher": "Harvard University Press",
            "publishedDate": "2014-04-14",
            "description": "To most of us, learning something the hard way implies needless effort. But research shows that when learning is hard, you're doing the important work that makes knowledge stick.",
            "pageCount": 336,
            "language": "en",
            "averageRating": 4.7,
            "ratingsCount": 2100,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780674729018"},
                {"type": "ISBN_10", "identifier": "0674729013"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=jN7XAwAAQBAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "mindset": {
        "volumeInfo": {
            "title": "Mindset: The New Psychology of Success",
            "authors": ["Carol S. Dweck"],
            "publisher": "Ballantine Books",
            "publishedDate": "2007-12-26",
            "description": "World-renowned Stanford University psychologist Carol E. Dweck shows how success in school, work, sports, the arts, and almost every area of human endeavor can be dramatically influenced by how we think about our talents and abilities.",
            "pageCount": 320,
            "language": "en",
            "averageRating": 4.6,
            "ratingsCount": 3500,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780345532589"},
                {"type": "ISBN_10", "identifier": "0345532589"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=fdjqz0TPL2wC&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "clean code": {
        "volumeInfo": {
            "title": "Clean Code: A Handbook of Agile Software Craftsmanship",
            "authors": ["Robert C. Martin"],
            "publisher": "Prentice Hall",
            "publishedDate": "2008-08-01",
            "description": "Even bad code can function. But if code isn't clean, it can bring a development organization to its knees. Every year, countless hours and significant resources are lost because of poorly written code.",
            "pageCount": 464,
            "language": "en",
            "averageRating": 4.7,
            "ratingsCount": 3100,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780132350884"},
                {"type": "ISBN_10", "identifier": "0132350882"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=_i6bDeoCQzsC&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "introduction to algorithms": {
        "volumeInfo": {
            "title": "Introduction to Algorithms",
            "authors": ["Thomas H. Cormen", "Charles E. Leiserson", "Ronald L. Rivest", "Clifford Stein"],
            "publisher": "MIT Press",
            "publishedDate": "2009-07-31",
            "description": "A comprehensive update of the leading algorithms text, with new material on matchings in bipartite graphs, online algorithms, machine learning, and other topics.",
            "pageCount": 1312,
            "language": "en",
            "averageRating": 4.6,
            "ratingsCount": 2400,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780262033848"},
                {"type": "ISBN_10", "identifier": "0262033844"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=i-bUBQAAQBAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "the pragmatic programmer": {
        "volumeInfo": {
            "title": "The Pragmatic Programmer: Your Journey to Mastery",
            "authors": ["Andrew Hunt", "David Thomas"],
            "publisher": "Addison-Wesley Professional",
            "publishedDate": "2019-09-13",
            "description": "Straight from the programming trenches, The Pragmatic Programmer cuts through the increasing specialization and technicalities of modern software development to examine the core process.",
            "pageCount": 352,
            "language": "en",
            "averageRating": 4.7,
            "ratingsCount": 2800,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780135957059"},
                {"type": "ISBN_10", "identifier": "0135957052"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=5wBQAAAAMAAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "python crash course": {
        "volumeInfo": {
            "title": "Python Crash Course",
            "authors": ["Eric Matthes"],
            "publisher": "No Starch Press",
            "publishedDate": "2019-05-03",
            "description": "A fast-paced, thorough introduction to programming with Python that will have you writing programs, solving problems, and making things that work in no time.",
            "pageCount": 544,
            "language": "en",
            "averageRating": 4.7,
            "ratingsCount": 2600,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9781593279288"},
                {"type": "ISBN_10", "identifier": "1593279280"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=i9eEDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "atomic habits": {
        "volumeInfo": {
            "title": "Atomic Habits",
            "authors": ["James Clear"],
            "publisher": "Avery",
            "publishedDate": "2018-10-16",
            "description": "No matter your goals, Atomic Habits offers a proven framework for improving—every day. James Clear, one of the world's leading experts on habit formation, reveals practical strategies that will teach you exactly how to form good habits, break bad ones, and master the tiny behaviors that lead to remarkable results.",
            "pageCount": 320,
            "language": "en",
            "averageRating": 4.8,
            "ratingsCount": 4600,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780735211292"},
                {"type": "ISBN_10", "identifier": "0735211299"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=XfFvDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "the psychology of money": {
        "volumeInfo": {
            "title": "The Psychology of Money",
            "authors": ["Morgan Housel"],
            "publisher": "Harriman House",
            "publishedDate": "2020-09-08",
            "description": "Doing well with money isn't necessarily about what you know. It's about how you behave. And behavior is hard to teach, even to really smart people. Money—investing, personal finance, and business decisions—is typically taught as a math-based field.",
            "pageCount": 256,
            "language": "en",
            "averageRating": 4.7,
            "ratingsCount": 3200,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780857197689"},
                {"type": "ISBN_10", "identifier": "0857197681"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=43fGDwAAQBAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "rich dad poor dad": {
        "volumeInfo": {
            "title": "Rich Dad Poor Dad",
            "authors": ["Robert T. Kiyosaki"],
            "publisher": "Plata Publishing",
            "publishedDate": "2017-04-11",
            "description": "Rich Dad Poor Dad is Robert's story of growing up with two dads—his real father and the father of his best friend, his rich dad—and the ways in which both men shaped his thoughts about money and investing.",
            "pageCount": 336,
            "language": "en",
            "averageRating": 4.6,
            "ratingsCount": 3400,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9781612680194"},
                {"type": "ISBN_10", "identifier": "1612680194"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=Zl_4DwAAQBAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "zero to one": {
        "volumeInfo": {
            "title": "Zero to One: Notes on Startups",
            "authors": ["Peter Thiel", "Blake Masters"],
            "publisher": "Crown Business",
            "publishedDate": "2014-09-16",
            "description": "If you want to build a better future, you must believe in secrets. The great secret of our time is that there are still uncharted frontiers to explore and new inventions to create.",
            "pageCount": 224,
            "language": "en",
            "averageRating": 4.5,
            "ratingsCount": 2700,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780804139298"},
                {"type": "ISBN_10", "identifier": "0804139296"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=V2c8BAAAQBAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "why we sleep": {
        "volumeInfo": {
            "title": "Why We Sleep: Unlocking the Power of Sleep and Dreams",
            "authors": ["Matthew Walker"],
            "publisher": "Scribner",
            "publishedDate": "2017-10-03",
            "description": "A fascinating dive into the purpose and power of slumber, exploring how sleep affects every aspect of our physical and mental well-being.",
            "pageCount": 368,
            "language": "en",
            "averageRating": 4.7,
            "ratingsCount": 2900,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9781501144318"},
                {"type": "ISBN_10", "identifier": "1501144316"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=8U2oAAAAQBAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
    "outlive": {
        "volumeInfo": {
            "title": "Outlive: The Science and Art of Longevity",
            "authors": ["Peter Attia", "Bill Gifford"],
            "publisher": "Harmony",
            "publishedDate": "2023-03-28",
            "description": "A groundbreaking manifesto on living better and longer that challenges the conventional medical thinking on aging and reveals a new approach to preventing chronic disease.",
            "pageCount": 496,
            "language": "en",
            "averageRating": 4.7,
            "ratingsCount": 2300,
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780593236598"},
                {"type": "ISBN_10", "identifier": "0593236599"},
            ],
            "imageLinks": {
                "thumbnail": "https://books.google.com/books/content?id=d1MNEAAAQBAJ&printsec=frontcover&img=1&zoom=1"
            },
        }
    },
}


class Command(BaseCommand):
    help = "Imports real books from Google Books API and populates categories."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.google_placeholder_hash = None

    def add_arguments(self, parser):
        parser.add_argument(
            "--per-category",
            type=int,
            default=12,
            help="Number of books to import per category (default: 12)",
        )
        parser.add_argument(
            "--clear-dummy",
            action="store_true",
            help="Delete seed dummy books without orders, and deactivate dummy books with orders.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the import without saving any changes to the database.",
        )
        parser.add_argument(
            "--curated",
            action="store_true",
            help="Import curated list of 20+ books with covers instead of subject searches.",
        )

    def _get_api_key(self):
        """Read optional GOOGLE_BOOKS_API_KEY from environment or .env file."""
        key = os.getenv("GOOGLE_BOOKS_API_KEY", "").strip()
        if key:
            return key

        search_dirs = [settings.BASE_DIR, settings.BASE_DIR.parent]
        for sdir in search_dirs:
            env_file = sdir / ".env"
            if env_file.exists():
                try:
                    with open(env_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("GOOGLE_BOOKS_API_KEY="):
                                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                                if val:
                                    return val
                except Exception:
                    pass
        return None

    def _get_google_placeholder_hash(self):
        """Fetch Google placeholder image once at runtime and return its SHA-256 hash."""
        try:
            resp = requests.get(
                GOOGLE_PLACEHOLDER_URL,
                headers={"User-Agent": "BookstoreImporter/1.0"},
                timeout=10,
            )
            if resp.status_code == 200 and resp.content:
                placeholder_hash = hashlib.sha256(resp.content).hexdigest()
                self.stdout.write(f"Google placeholder hash: {placeholder_hash}")
                return placeholder_hash
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Google placeholder returned HTTP {resp.status_code}"
                    )
                )
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"Could not fetch Google placeholder hash: {e}")
            )
        return None

    def _clean_description(self, raw_desc):
        """Strip HTML tags, unescape HTML entities, and trim to 1500 chars."""
        if not raw_desc:
            return ""
        cleaned = re.sub(r"<[^>]+>", " ", str(raw_desc))
        cleaned = html.unescape(cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned[:1500].strip()

    def _extract_cover_url(self, volume_info):
        """
        Use imageLinks URL as given (https), upgrading to the largest available
        (extraLarge, large, medium, small, thumbnail in that order).
        Do NOT replace zoom=1 with zoom=2.
        """
        image_links = volume_info.get("imageLinks") or {}
        url = ""
        for key in ["extraLarge", "large", "medium", "small", "thumbnail"]:
            if image_links.get(key):
                url = image_links[key]
                break
        if not url:
            return ""
        if url.startswith("http://"):
            url = "https://" + url[7:]
        return url

    def _validate_cover(self, content, content_type):
        """
        Validate cover image:
        - content-type image/*
        - size under 2 MB
        - size above 4 KB
        - Pillow can open it
        - width >= 150 and height >= 200
        - SHA-256 hash is NOT Google's placeholder hash
        """
        if not content:
            return False, "Empty image content"

        if not content_type or "image" not in content_type.lower():
            return False, f"Non-image Content-Type: {content_type}"

        if len(content) > 2 * 1024 * 1024:
            return False, f"File size too large: {len(content)} bytes"

        if len(content) <= 4 * 1024:
            return False, f"File size too small: {len(content)} bytes"

        try:
            with Image.open(io.BytesIO(content)) as img:
                width, height = img.size
                if width < 150 or height < 200:
                    return False, f"Image dimensions too small: {width}x{height} (min 150x200)"
        except Exception as e:
            return False, f"Pillow cannot open image: {e}"

        content_hash = hashlib.sha256(content).hexdigest()
        if self.google_placeholder_hash and content_hash == self.google_placeholder_hash:
            return False, "Image matches Google placeholder hash"

        return True, None

    def _download_and_validate(self, url, timeout=10):
        """Download image from url and validate it."""
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                headers={"User-Agent": "BookstoreImporter/1.0"},
            )
            if resp.status_code != 200:
                return None, f"HTTP {resp.status_code}"
            content_type = resp.headers.get("Content-Type", "").lower()
            is_valid, err = self._validate_cover(resp.content, content_type)
            if not is_valid:
                return None, err
            return resp.content, None
        except requests.exceptions.RequestException as e:
            return None, str(e)

    def _fetch_valid_cover(self, volume_info):
        """
        Try Google cover first. If Google has no valid cover and volume has an
        ISBN_13 or ISBN_10 (industryIdentifiers), try Open Library:
        https://covers.openlibrary.org/b/isbn/<ISBN>-L.jpg?default=false
        Apply the same validation. Returns (content_bytes, None) or (None, err).
        """
        google_url = self._extract_cover_url(volume_info)
        if google_url:
            content, err = self._download_and_validate(google_url)
            if content:
                return content, None

        # FALLBACK: Open Library using industryIdentifiers
        industry_ids = volume_info.get("industryIdentifiers") or []
        isbn_13_list = [
            item["identifier"].strip()
            for item in industry_ids
            if item.get("type") == "ISBN_13" and item.get("identifier")
        ]
        isbn_10_list = [
            item["identifier"].strip()
            for item in industry_ids
            if item.get("type") == "ISBN_10" and item.get("identifier")
        ]
        isbns = isbn_13_list + isbn_10_list

        for raw_isbn in isbns:
            clean_isbn = "".join(c for c in raw_isbn if c.isdigit() or c in ("X", "x"))
            if not clean_isbn:
                continue
            ol_url = f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-L.jpg?default=false"
            content, err = self._download_and_validate(ol_url, timeout=15)
            if content:
                return content, None

        return None, "No valid cover from Google Books or Open Library"

    def _is_valid_cover_on_disk(self, book):
        """Check if an existing book in DB has a real valid cover file on disk."""
        if not book.cover_image or not book.cover_image.name:
            return False
        try:
            path = book.cover_image.path
            if not os.path.exists(path):
                return False
            with Image.open(path) as img:
                if img.width < 150 or img.height < 200:
                    return False
            with open(path, "rb") as f:
                content = f.read()
            if len(content) <= 4 * 1024:
                return False
            h = hashlib.sha256(content).hexdigest()
            if self.google_placeholder_hash and h == self.google_placeholder_hash:
                return False
            return True
        except Exception:
            return False

    def _generate_price_and_stock(self, sale_info):
        """Determine realistic price (in INR), old_price, and stock."""
        sale_info = sale_info or {}
        list_price = sale_info.get("listPrice") or sale_info.get("retailPrice") or {}
        if list_price.get("amount") and list_price.get("currencyCode") == "INR":
            price = Decimal(str(round(float(list_price["amount"]), 2)))
        else:
            raw = random.randint(199, 899)
            tens = round(raw / 10) * 10
            price_int = tens - 1
            if price_int < 199:
                price_int = 199
            elif price_int > 899:
                price_int = 899
            price = Decimal(str(price_int))

        multiplier = random.uniform(1.25, 1.8)
        calc_old = float(price) * multiplier
        old_tens = round(calc_old / 10.0) * 10
        if old_tens <= float(price):
            old_tens = (round(float(price) / 10.0) + 1) * 10
        old_price = Decimal(str(old_tens))

        stock = random.randint(10, 80)
        return price, old_price, stock

    def _extract_rating_and_reviews(self, volume_info):
        """Extract rating and reviews_count with realistic fallback."""
        avg_rating = volume_info.get("averageRating")
        if avg_rating is not None:
            try:
                rating = round(float(avg_rating), 1)
                rating = max(0.0, min(5.0, rating))
            except (ValueError, TypeError):
                rating = round(random.uniform(3.8, 4.7), 1)
        else:
            rating = round(random.uniform(3.8, 4.7), 1)

        ratings_count = volume_info.get("ratingsCount")
        if ratings_count is not None:
            try:
                reviews_count = int(ratings_count)
            except (ValueError, TypeError):
                reviews_count = random.randint(80, 2500)
        else:
            reviews_count = random.randint(80, 2500)

        return rating, reviews_count

    def _normalize_date(self, date_str):
        """Normalize YYYY, YYYY-MM, or YYYY-MM-DD into a sortable date string."""
        if not date_str:
            return "1900-01-01"
        parts = str(date_str).strip().split("-")
        year = parts[0] if len(parts) > 0 and parts[0].isdigit() else "1900"
        month = parts[1] if len(parts) > 1 and parts[1].isdigit() else "01"
        day = parts[2] if len(parts) > 2 and parts[2].isdigit() else "01"
        return f"{year.zfill(4)}-{month.zfill(2)}-{day.zfill(2)}"

    def _fetch_volumes(self, query, api_key=None, max_retries=3):
        """Fetch volumes from Google Books API for category search."""
        params = {
            "q": query,
            "maxResults": 20,
            "printType": "books",
            "langRestrict": "en",
            "orderBy": "relevance",
        }
        if api_key:
            params["key"] = api_key

        url = "https://www.googleapis.com/books/v1/volumes"
        headers = {"User-Agent": "BookstoreImporter/1.0"}

        for attempt in range(max_retries + 1):
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=10)
                if resp.status_code == 429:
                    if attempt < max_retries:
                        time.sleep(2)
                        continue
                    return None, f"HTTP 429 Rate limit exceeded after {max_retries} retries"
                resp.raise_for_status()
                data = resp.json()
                items = data.get("items", [])
                return items, None
            except requests.exceptions.Timeout:
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                return None, "Request timeout"
            except requests.exceptions.RequestException as e:
                return None, f"Request error: {str(e)}"
            except ValueError:
                return None, "Invalid JSON received"

        return None, "Unknown error during API request"

    def _fetch_curated_volumes(self, title, author, api_key=None, max_retries=2):
        """
        Call https://www.googleapis.com/books/v1/volumes?q=intitle:"<title>"+inauthor:"<author>"&maxResults=5
        """
        url = f'https://www.googleapis.com/books/v1/volumes?q=intitle:"{requests.utils.quote(title)}"+inauthor:"{requests.utils.quote(author)}"&maxResults=5'
        if api_key:
            url += f"&key={api_key}"

        headers = {"User-Agent": "BookstoreImporter/1.0"}

        for attempt in range(max_retries + 1):
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 429:
                    if attempt < max_retries:
                        time.sleep(1.5)
                        continue
                    return None, "HTTP 429 Rate limit exceeded"
                resp.raise_for_status()
                data = resp.json()
                items = data.get("items", [])
                return items, None
            except requests.exceptions.RequestException as e:
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                return None, str(e)
            except ValueError:
                return None, "Invalid JSON received"
        return None, "Failed to fetch curated volumes"

    def _recompute_featured_flags(self, dry_run=False, book_records=None):
        """
        Recompute featured flags using ONLY books that have valid covers:
        - 4 highest rated = is_best_seller
        - 4 newest by publishedDate = is_new_arrival
        - all others False
        """
        self.stdout.write(self.style.MIGRATE_HEADING("\nConfiguring Best Sellers and New Arrivals..."))

        date_map = {}
        if book_records:
            for rec in book_records:
                b = rec.get("book")
                if b and rec.get("published_date"):
                    date_map[b.id] = rec["published_date"]

        active_books = list(Book.objects.filter(is_active=True))
        valid_candidates = []

        for b in active_books:
            # Check that cover is valid on disk
            if self._is_valid_cover_on_disk(b):
                pub_date = date_map.get(b.id)
                if not pub_date:
                    pub_date = b.created_at.strftime("%Y-%m-%d") if b.created_at else "1900-01-01"
                valid_candidates.append({
                    "book": b,
                    "rating": b.rating,
                    "published_date": pub_date,
                    "title": b.title,
                })

        if not dry_run:
            Book.objects.all().update(is_best_seller=False, is_new_arrival=False)

        # 4 highest rated
        by_rating = sorted(valid_candidates, key=lambda x: x["rating"], reverse=True)
        top_best_sellers = by_rating[:4]
        best_seller_ids = [rec["book"].id for rec in top_best_sellers]

        self.stdout.write(self.style.SUCCESS("Top 4 Best Sellers (highest rating with valid cover):"))
        for rec in top_best_sellers:
            self.stdout.write(f"  * {rec['title']} (Rating: {rec['rating']})")

        # 4 newest by publishedDate
        by_date = sorted(valid_candidates, key=lambda x: x["published_date"], reverse=True)
        top_new_arrivals = by_date[:4]
        new_arrival_ids = [rec["book"].id for rec in top_new_arrivals]

        self.stdout.write(self.style.SUCCESS("Top 4 New Arrivals (newest published date with valid cover):"))
        for rec in top_new_arrivals:
            self.stdout.write(f"  + {rec['title']} (Published: {rec['published_date']})")

        if not dry_run:
            if best_seller_ids:
                Book.objects.filter(id__in=best_seller_ids).update(is_best_seller=True)
            if new_arrival_ids:
                Book.objects.filter(id__in=new_arrival_ids).update(is_new_arrival=True)

    def handle_clear_dummy(self, dry_run=False):
        """Delete seed dummy books without orders; deactivate those with orders."""
        self.stdout.write(self.style.NOTICE("Clearing old seed dummy books..."))
        all_books = Book.objects.all()
        dummy_candidates = [
            b for b in all_books
            if b.title.strip().lower() in DUMMY_TITLES or not b.cover_image
        ]

        deleted_count = 0
        deactivated_count = 0

        for book in dummy_candidates:
            if book.order_items.exists():
                deactivated_count += 1
                if not dry_run:
                    book.is_active = False
                    book.save(update_fields=["is_active"])
                self.stdout.write(
                    self.style.WARNING(
                        f"  [PROTECTED] Cannot delete '{book.title}' because it has existing orders. Deactivated it instead."
                    )
                )
            else:
                deleted_count += 1
                title = book.title
                if not dry_run:
                    book.delete()
                self.stdout.write(f"  [DELETED] Dummy book: '{title}'")

        action_str = "Would delete" if dry_run else "Deleted"
        deact_str = "Would deactivate" if dry_run else "Deactivated"
        self.stdout.write(
            self.style.SUCCESS(
                f"Dummy data cleanup: {action_str} {deleted_count} book(s), {deact_str} {deactivated_count} book(s) with orders."
            )
        )

    def handle_curated(self, dry_run=False, api_key=None):
        """
        Import curated list of 20+ books with covers instead of subject searches.
        Pick the first result that has a valid cover, language 'en', and a description.
        Make idempotent and skip duplicates.
        """
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== IMPORTING CURATED BOOKS (20+) ==="))

        created_titles = []
        missing_cover_titles = []
        imported_records = []

        seen_pairs = set()
        seen_slugs = set()
        for b in Book.objects.all():
            seen_pairs.add((b.title.strip().lower(), b.author.strip().lower()))
            seen_slugs.add(b.slug.strip().lower())

        category_cache = {}
        for entry in CURATED_ENTRIES:
            cat_name = entry["category"]
            if cat_name not in category_cache:
                cat_icon = CATEGORY_ICONS.get(cat_name, "bi-book")
                if not dry_run:
                    category, _ = Category.objects.get_or_create(
                        name=cat_name,
                        defaults={"icon": cat_icon},
                    )
                    if cat_icon and category.icon != cat_icon:
                        category.icon = cat_icon
                        category.save(update_fields=["icon"])
                    category_cache[cat_name] = category
                else:
                    category_cache[cat_name] = Category(name=cat_name, icon=cat_icon)

        for entry in CURATED_ENTRIES:
            target_title = entry["title"]
            target_author = entry["author"]
            cat_name = entry["category"]
            category = category_cache[cat_name]

            # Check duplicate (same title and author)
            pair = (target_title.strip().lower(), target_author.strip().lower())
            if pair in seen_pairs:
                self.stdout.write(
                    self.style.NOTICE(
                        f"  [SKIPPED] Duplicate: '{target_title}' by {target_author} already exists."
                    )
                )
                existing_book = Book.objects.filter(
                    title__iexact=target_title.strip(),
                    author__icontains=target_author.split()[-1],
                ).first()
                if existing_book:
                    fallback_entry = CURATED_FALLBACK_VOLUMES.get(target_title.lower(), {})
                    pub_date = self._normalize_date(
                        fallback_entry.get("volumeInfo", {}).get("publishedDate")
                    )
                    imported_records.append({
                        "book": existing_book,
                        "rating": existing_book.rating,
                        "published_date": pub_date,
                        "title": existing_book.title,
                    })
                continue

            self.stdout.write(f"\nSearching curated book: '{target_title}' by {target_author}...")
            items, err = self._fetch_curated_volumes(target_title, target_author, api_key=api_key)
            time.sleep(0.3)

            chosen_item = None
            chosen_cover_bytes = None

            if items:
                for item in items:
                    vol = item.get("volumeInfo") or {}
                    lang = (vol.get("language") or "").strip().lower()
                    if lang not in ("en", "eng"):
                        continue
                    clean_desc = self._clean_description(vol.get("description", ""))
                    if not clean_desc:
                        continue
                    cover_bytes, cov_err = self._fetch_valid_cover(vol)
                    if cover_bytes:
                        chosen_item = item
                        chosen_cover_bytes = cover_bytes
                        break

            # If no live API result with valid cover, check curated fallback volume
            if not chosen_item or not chosen_cover_bytes:
                fallback_item = CURATED_FALLBACK_VOLUMES.get(target_title.lower())
                if fallback_item:
                    fallback_vol = fallback_item.get("volumeInfo") or {}
                    cover_bytes, cov_err = self._fetch_valid_cover(fallback_vol)
                    if cover_bytes:
                        chosen_item = fallback_item
                        chosen_cover_bytes = cover_bytes

            if not chosen_item or not chosen_cover_bytes:
                self.stdout.write(
                    self.style.WARNING(
                        f"  [NO VALID COVER] Could not find valid cover for '{target_title}' by {target_author}."
                    )
                )
                missing_cover_titles.append(f"'{target_title}' by {target_author}")
                continue

            # Process volume and create book
            vol = chosen_item.get("volumeInfo") or {}
            title = (vol.get("title") or target_title).strip()
            authors_list = vol.get("authors") or [target_author]
            authors_str = ", ".join([a.strip() for a in authors_list if a.strip()]) or target_author
            clean_desc = self._clean_description(vol.get("description", ""))

            sale_info = chosen_item.get("saleInfo") or {}
            price, old_price, stock = self._generate_price_and_stock(sale_info)
            rating, reviews_count = self._extract_rating_and_reviews(vol)

            publisher = (vol.get("publisher") or "").strip()[:255]
            page_count = vol.get("pageCount")
            pages = int(page_count) if isinstance(page_count, int) and page_count > 0 else None
            raw_lang = (vol.get("language") or "en").strip().lower()
            language = "English" if raw_lang in ("en", "eng") else raw_lang.capitalize()
            published_date_norm = self._normalize_date(vol.get("publishedDate"))

            candidate_slug = slugify(title) or "book"
            slug = candidate_slug
            counter = 1
            while slug in seen_slugs or Book.objects.filter(slug=slug).exists():
                slug = f"{candidate_slug}-{counter}"
                counter += 1

            seen_pairs.add(pair)
            seen_slugs.add(slug)

            book = None
            if not dry_run:
                with transaction.atomic():
                    book = Book(
                        title=title,
                        slug=slug,
                        author=authors_str,
                        category=category,
                        price=price,
                        old_price=old_price,
                        rating=rating,
                        reviews_count=reviews_count,
                        publisher=publisher,
                        language=language,
                        pages=pages,
                        stock=stock,
                        is_best_seller=False,
                        is_new_arrival=False,
                        is_active=True,
                        description=clean_desc,
                    )
                    book.cover_image.save(f"{slug}.jpg", ContentFile(chosen_cover_bytes), save=False)
                    book.save()

            imported_records.append({
                "book": book,
                "rating": rating,
                "published_date": published_date_norm,
                "title": title,
            })

            created_titles.append(f"'{title}' by {authors_str}")
            self.stdout.write(self.style.SUCCESS(f"  + Created: '{title}' by {authors_str} [Rs. {price}]"))

        # Summary of curated import
        self.stdout.write(self.style.MIGRATE_HEADING("\n" + "=" * 55))
        self.stdout.write(self.style.MIGRATE_HEADING("CURATED IMPORT SUMMARY"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 55))
        self.stdout.write(f"Total curated entries: {len(CURATED_ENTRIES)}")
        self.stdout.write(f"Created: {len(created_titles)}")
        self.stdout.write(f"Could not be found with valid cover: {len(missing_cover_titles)}")

        self.stdout.write(self.style.SUCCESS("\nCreated Titles:"))
        for t in created_titles:
            self.stdout.write(f"  + {t}")

        if missing_cover_titles:
            self.stdout.write(self.style.WARNING("\nTitles without valid cover:"))
            for t in missing_cover_titles:
                self.stdout.write(f"  - {t}")
        else:
            self.stdout.write(self.style.SUCCESS("\nAll curated titles were created with valid covers!"))

        # Recompute featured flags
        self._recompute_featured_flags(dry_run=dry_run, book_records=imported_records)

    def handle_categories(self, per_category=12, dry_run=False, api_key=None):
        """Subject search category import flow."""
        created_per_category = {}
        skipped_stats = {
            "missing_fields": 0,
            "duplicate": 0,
            "cover_download_failed": 0,
        }
        failed_queries = 0
        imported_records = []
        seen_pairs = set()
        seen_slugs = set()

        for b in Book.objects.all():
            seen_pairs.add((b.title.strip().lower(), b.author.strip().lower()))
            seen_slugs.add(b.slug.strip().lower())

        for cat_cfg in CATEGORIES_CONFIG:
            cat_name = cat_cfg["name"]
            cat_icon = cat_cfg["icon"]
            queries = cat_cfg["queries"]

            if not dry_run:
                category, _ = Category.objects.get_or_create(
                    name=cat_name,
                    defaults={"icon": cat_icon},
                )
                if cat_icon and category.icon != cat_icon:
                    category.icon = cat_icon
                    category.save(update_fields=["icon"])
            else:
                category = Category(name=cat_name, icon=cat_icon)

            created_per_category[cat_name] = 0
            self.stdout.write(self.style.MIGRATE_HEADING(f"\nProcessing Category: {cat_name} (target: {per_category})"))

            collected_items = []
            for query in queries:
                if len(collected_items) >= per_category * 2:
                    break
                items, err = self._fetch_volumes(query, api_key=api_key)
                time.sleep(0.3)

                if err or items is None:
                    self.stdout.write(self.style.WARNING(f"  Live query '{query}' failed: {err}"))
                    failed_queries += 1
                else:
                    self.stdout.write(f"  Live query '{query}' returned {len(items)} volumes.")
                    collected_items.extend(items)

            if len(collected_items) < per_category:
                fallback_items = FALLBACK_VOLUMES.get(cat_name, [])
                self.stdout.write(
                    self.style.NOTICE(f"  Adding {len(fallback_items)} curated real Google Books volumes for {cat_name}.")
                )
                collected_items.extend(fallback_items)

            for item in collected_items:
                if created_per_category[cat_name] >= per_category:
                    break

                vol = item.get("volumeInfo") or {}
                title = (vol.get("title") or "").strip()
                authors_list = vol.get("authors") or []
                authors_str = ", ".join([a.strip() for a in authors_list if a.strip()])
                clean_desc = self._clean_description(vol.get("description", ""))

                if not title or not authors_str or not clean_desc:
                    skipped_stats["missing_fields"] += 1
                    continue

                pair = (title.lower(), authors_str.lower())
                candidate_slug = slugify(title) or "book"

                if pair in seen_pairs or candidate_slug in seen_slugs:
                    skipped_stats["duplicate"] += 1
                    continue

                sale_info = item.get("saleInfo") or {}
                price, old_price, stock = self._generate_price_and_stock(sale_info)
                rating, reviews_count = self._extract_rating_and_reviews(vol)

                publisher = (vol.get("publisher") or "").strip()[:255]
                page_count = vol.get("pageCount")
                pages = int(page_count) if isinstance(page_count, int) and page_count > 0 else None
                raw_lang = (vol.get("language") or "en").strip().lower()
                language = "English" if raw_lang in ("en", "eng") else raw_lang.capitalize()
                published_date_norm = self._normalize_date(vol.get("publishedDate"))

                # Validate and download cover (Google Books or Open Library fallback)
                cover_content, download_err = self._fetch_valid_cover(vol)
                if download_err or not cover_content:
                    skipped_stats["cover_download_failed"] += 1
                    self.stdout.write(self.style.WARNING(f"  Skip '{title}': Cover invalid ({download_err})"))
                    continue

                slug = candidate_slug
                counter = 1
                while slug in seen_slugs or Book.objects.filter(slug=slug).exists():
                    slug = f"{candidate_slug}-{counter}"
                    counter += 1

                seen_pairs.add(pair)
                seen_slugs.add(slug)

                book = None
                if not dry_run:
                    with transaction.atomic():
                        book = Book(
                            title=title,
                            slug=slug,
                            author=authors_str,
                            category=category,
                            price=price,
                            old_price=old_price,
                            rating=rating,
                            reviews_count=reviews_count,
                            publisher=publisher,
                            language=language,
                            pages=pages,
                            stock=stock,
                            is_best_seller=False,
                            is_new_arrival=False,
                            is_active=True,
                            description=clean_desc,
                        )
                        book.cover_image.save(f"{slug}.jpg", ContentFile(cover_content), save=False)
                        book.save()

                imported_records.append({
                    "book": book,
                    "rating": rating,
                    "published_date": published_date_norm,
                    "title": title,
                })

                created_per_category[cat_name] += 1
                self.stdout.write(f"  + Added: '{title}' by {authors_str} [Rs. {price}]")

        total_created = sum(created_per_category.values())
        total_skipped = sum(skipped_stats.values())

        self.stdout.write(self.style.MIGRATE_HEADING("\n" + "=" * 55))
        self.stdout.write(self.style.MIGRATE_HEADING("IMPORT SUMMARY"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 55))
        for cat_name, count in created_per_category.items():
            self.stdout.write(f"  - {cat_name}: {count} books")
        self.stdout.write(f"\nTotal books created: {total_created}")
        self.stdout.write(f"Total volumes skipped: {total_skipped}")
        self.stdout.write(f"  - Missing title/author/desc: {skipped_stats['missing_fields']}")
        self.stdout.write(f"  - Duplicates: {skipped_stats['duplicate']}")
        self.stdout.write(f"  - Cover invalid / failed: {skipped_stats['cover_download_failed']}")
        self.stdout.write(f"Failed API queries: {failed_queries}")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 55 + "\n"))

        self._recompute_featured_flags(dry_run=dry_run, book_records=imported_records)

    def handle(self, *args, **options):
        per_category = options.get("per_category", 12)
        clear_dummy = options.get("clear_dummy", False)
        dry_run = options.get("dry_run", False)
        curated = options.get("curated", False)

        if dry_run:
            self.stdout.write(self.style.WARNING("=== RUNNING IN DRY-RUN MODE (No DB changes) ==="))

        if clear_dummy:
            self.handle_clear_dummy(dry_run=dry_run)

        api_key = self._get_api_key()
        if api_key:
            self.stdout.write(self.style.SUCCESS("Google Books API Key found and configured."))
        else:
            self.stdout.write(
                self.style.NOTICE("No Google Books API Key found in environment. Proceeding unauthenticated.")
            )

        # Fetch Google placeholder hash once at the start of command
        self.google_placeholder_hash = self._get_google_placeholder_hash()

        if curated:
            self.handle_curated(dry_run=dry_run, api_key=api_key)
        else:
            self.handle_categories(per_category=per_category, dry_run=dry_run, api_key=api_key)

