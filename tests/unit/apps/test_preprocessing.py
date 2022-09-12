import pytest
from docarray import Document, DocumentArray

from now.apps.image_to_image.app import ImageToImage
from now.apps.image_to_text.app import ImageToText
from now.apps.music_to_music.app import MusicToMusic
from now.apps.text_to_image.app import TextToImage
from now.apps.text_to_text.app import TextToText
from now.apps.text_to_video.app import TextToVideo
from now.now_dataclasses import UserInput


def test_text_to_video_preprocessing_query():
    """Test if the text to video preprocessing works for queries"""
    app = TextToVideo()
    da = DocumentArray([Document(chunks=[Document(text='test')])])
    da = app.preprocess(da=da, user_input=UserInput())
    assert len(da) == 1
    assert len(da[0].chunks) == 1
    assert da[0].chunks[0].text == 'test'


def test_text_to_video_preprocessing_indexing():
    """Test if the text to video preprocessing works for indexing"""
    app = TextToVideo()
    da = DocumentArray([Document(uri='tests/resources/gif/folder1/file.gif')])
    da = app.preprocess(da=da, user_input=UserInput(), is_indexing=True)
    assert len(da) == 1
    assert len(da[0].chunks) == 3
    assert da[0].chunks[0].blob != b''


@pytest.mark.parametrize(
    'app_cls,is_indexing',
    [
        (TextToText, False),
        (TextToText, True),
        (TextToImage, False),
        (ImageToText, True),
    ],
)
def test_text_preprocessing(app_cls, is_indexing):
    """Test if the text to text preprocessing works for queries and indexing"""
    app = TextToText()
    da = DocumentArray([Document(text='test')])
    da = app.preprocess(da=da, user_input=UserInput(), is_indexing=is_indexing)
    assert len(da) == 1
    assert len(da[0].chunks) == 0
    assert da[0].text == 'test'


@pytest.mark.parametrize(
    'app_cls,is_indexing',
    [
        (ImageToImage, False),
        (ImageToImage, True),
        (ImageToText, False),
        (TextToImage, True),
    ],
)
def test_image_preprocessing(app_cls, is_indexing):
    """Test if the image to image preprocessing works for queries and indexing"""
    app = app_cls()
    da = DocumentArray([Document(uri='tests/resources/gif/folder1/file.gif')])
    da = app.preprocess(da=da, user_input=UserInput(), is_indexing=is_indexing)
    assert len(da) == 1
    assert len(da[0].chunks) == 0
    assert da[0].blob != b''


@pytest.mark.parametrize('is_indexing', [False, True])
def test_music_preprocessing(is_indexing):
    """Test if the music preprocessing works"""
    app = MusicToMusic()
    da = DocumentArray(
        [
            Document(
                uri='tests/resources/music/0ac463f952880e622bc15962f4f75ea51a1861a1.mp3'
            )
        ]
    )
    da = app.preprocess(da=da, user_input=UserInput())
    assert len(da) == 1
    assert len(da[0].chunks) == 0
    assert da[0].blob != b''