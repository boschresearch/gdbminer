// This source code is from tinyjson v 2.5.1
//   https://github.com/rhysd/tinyjson
// Copyright (c) 2016 rhysd
// This source code is licensed under the MIT license found in the
// 3rd-party-licenses.txt file in the root directory of this source tree.

use std::collections::HashMap;
use std::convert::TryFrom;
use std::fmt;
use std::io;
use std::ops::{Index, IndexMut};

const NULL: () = ();

use std::char;
use std::iter::Peekable;
use std::str::FromStr;

use std::io::{Write};

//use crate::json_value::{InnerAsRef, InnerAsRefMut, JsonValue};

/// Panic-safe JSON query for [`JsonValue`] value. This instance is usually created by [`JsonValue::query`]. It allows
/// accessing the nested elements of array or object easily with the following query methods.
///
/// - `.child("foo")`: Access by key of object
/// - `.child(0)`: Access by index of array
/// - `.child_by(|value| ...)`: Access by value predicate
///
/// [`JsonValue`] also supports to access nested elements with `[]` operators, but they panics when the element does
/// not exist like `Vec` or `HashMap`.
/// ```
/// use tinyjson::JsonValue;
///
/// let v: JsonValue = "[{\"foo\": [true, null, 1]}]".parse().unwrap();
///
/// // Find element which is larger than zero
/// let found =
///     v.query()
///         // Find the first element {"foo": [-1, 0, 1]} of the array
///         .child(0)
///         // Find the value of object by key "foo": [-1, 0, 1]
///         .child("foo")
///         // Find the first value which is greater than zero: 1
///         .child_by(|v| matches!(v, JsonValue::Number(f) if *f > 0.0))
///         // Get the found value as `f64`
///         .get::<f64>();
/// assert_eq!(found, Some(&1.0));
///
/// // You can reuse the query
/// let array = v.query().child(0).child("foo");
/// let first: &bool = array.child(0).get().unwrap();
/// let second: &() = array.child(1).get().unwrap();
/// let third: &f64 = array.child(2).get().unwrap();
/// ```
#[derive(Default, Clone)]
pub struct JsonQuery<'val>(Option<&'val JsonValue>);

impl<'val> JsonQuery<'val> {
    /// Create a new `JsonQuery` instance.
    pub fn new(v: &'val JsonValue) -> Self {
        Self(Some(v))
    }

    /// Query for accessing value's elements by `usize` index (for array) or by `&str` key (for object).
    ///
    /// ```
    /// use tinyjson::JsonValue;
    ///
    /// let v: JsonValue = "[-1, 0, 1]".parse().unwrap();
    ///
    /// assert_eq!(v.query().child(0).find(), Some(&JsonValue::Number(-1.0)));
    /// assert_eq!(v.query().child("foo").find(), None);
    /// ```
    pub fn child<I: ChildIndex>(&self, index: I) -> Self {
        index.index(self)
    }

    /// Query for accessing value's elements by a value predicate. The predicate is a callback which takes a reference
    /// to the [`JsonValue`] reference and returns `true` when the value should be selected.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    ///
    /// let v: JsonValue = "[-1, 0, 1]".parse().unwrap();
    ///
    /// // Find element which is larger than zero
    /// let num_greater_than_zero =
    ///     v.query()
    ///         .child_by(|v| matches!(v, JsonValue::Number(f) if *f > 0.0))
    ///         .find();
    /// assert_eq!(num_greater_than_zero, Some(&JsonValue::from(1.0)));
    /// ```
    pub fn child_by<F>(&self, mut predicate: F) -> Self
    where
        F: FnMut(&JsonValue) -> bool,
    {
        match &self.0 {
            Some(JsonValue::Array(a)) => Self(a.iter().find(|v| predicate(v))),
            Some(JsonValue::Object(o)) => Self(o.values().find(|v| predicate(v))),
            _ => Self(None),
        }
    }

    /// Get the immutable reference to [`JsonValue`] corresponding to the query. If the value does not exist,
    /// it returns `None`.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    ///
    /// let v: JsonValue = "[-1, 0, 1]".parse().unwrap();
    ///
    /// assert_eq!(v.query().child(1).find(), Some(&JsonValue::Number(0.0)));
    /// assert_eq!(v.query().child(5).find(), None);
    /// ```
    pub fn find(&self) -> Option<&'val JsonValue> {
        self.0
    }

    /// Check if the value corresponding to the query exists or not.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    ///
    /// let v: JsonValue = "[-1, 0, 1]".parse().unwrap();
    ///
    /// assert!(v.query().child(1).exists());
    /// assert!(!v.query().child(5).exists());
    /// ```
    pub fn exists(&self) -> bool {
        self.0.is_some()
    }

    /// Get inner reference to the `JsonValue` value corresponding to the query. This is similar to [`JsonValue::get`].
    /// It returns `None` when the value does not exist or type does not match.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    ///
    /// let v: JsonValue = "[-1, 0, 1]".parse().unwrap();
    ///
    /// // Get the second element 0.0
    /// assert_eq!(v.query().child(1).get::<f64>(), Some(&0.0));
    /// // It's not a string value
    /// assert_eq!(v.query().child(1).get::<String>(), None);
    /// // Index is out of bounds
    /// assert_eq!(v.query().child(5).get::<f64>(), None);
    /// ```
    pub fn get<T: InnerAsRef>(&self) -> Option<&'val T> {
        self.0.and_then(|v| v.get())
    }
}

/// Panic-safe JSON query for [`JsonValue`] value. This instance is usually created by [`JsonValue::query_mut`].
/// It allows modifying the nested elements of array or object easily with the following query methods.
///
/// - `.child("foo")`: Access by key of object
/// - `.child(0)`: Access by index of array
/// - `.child_by(|value| ...)`: Access by value predicate
///
/// [`JsonValue`] also supports to access nested elements with `[]` operators, but they panics when the element does
/// not exist like `Vec` or `HashMap`.
///
/// Unlike [`JsonQuery`], methods of this type moves `self` since Rust does not allow to copy mutable references.
/// ```
/// use tinyjson::JsonValue;
///
/// let mut v: JsonValue = "[{\"foo\": [-1, 0, 1]}]".parse().unwrap();
///
/// // Find element which is larger than zero
/// let Some(mut found) =
///     v.query_mut()
///         // Find the first element {"foo": [-1, 0, 1]} of the array
///         .child(0)
///         // Find the value of object by key "foo": [-1, 0, 1]
///         .child("foo")
///         // Find the first value which is greater than zero: 1
///         .child_by(|v| matches!(v, JsonValue::Number(f) if *f > 0.0))
///         // Get the found value as `f64`
///         .get::<f64>() else { panic!() };
/// *found *= 3.0;
/// assert_eq!(v.stringify().unwrap(), "[{\"foo\":[-1,0,3]}]");
/// ```
#[derive(Default)]
pub struct JsonQueryMut<'val>(Option<&'val mut JsonValue>);

impl<'val> JsonQueryMut<'val> {
    /// Create a new `JsonQueryMut` instance.
    pub fn new(v: &'val mut JsonValue) -> Self {
        Self(Some(v))
    }

    /// Query for modifying value's elements by `usize` index (for array) or by `&str` key (for object).
    ///
    /// Unlike [`JsonQuery::child`], this moves `self` value since `JsonQueryMut` contains mutable reference to the
    /// value and mutable reference is not allowed to be copied.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    ///
    /// let mut v: JsonValue = "[-1, 0, 1]".parse().unwrap();
    ///
    /// if let Some(mut f) = v.query_mut().child(0).get::<f64>() {
    ///     *f *= 2.0;
    /// }
    /// assert_eq!(v.stringify().unwrap(), "[-2,0,1]");
    /// assert_eq!(v.query_mut().child("foo").find(), None);
    /// ```
    pub fn child<I: ChildIndex>(self, index: I) -> Self {
        index.index_mut(self)
    }

    /// Query for modifying value's elements by a value predicate. The predicate is a callback which takes a reference
    /// to the [`JsonValue`] reference and returns `true` when the value should be selected.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    ///
    /// let mut v: JsonValue = "[-1, 0, 1]".parse().unwrap();
    ///
    /// // Find a number greater than zero and modify the number
    /// if let Some(num) =
    ///     v.query_mut()
    ///         .child_by(|v| matches!(v, JsonValue::Number(f) if *f > 0.0))
    ///         .get::<f64>()
    /// {
    ///     *num *= 2.0;
    /// }
    /// assert_eq!(v.stringify().unwrap(), "[-1,0,2]");
    /// ```
    pub fn child_by<F>(self, mut predicate: F) -> Self
    where
        F: FnMut(&JsonValue) -> bool,
    {
        match self.0 {
            Some(JsonValue::Array(a)) => Self(a.iter_mut().find(|v| predicate(v))),
            Some(JsonValue::Object(o)) => Self(o.values_mut().find(|v| predicate(v))),
            _ => Self(None),
        }
    }

    /// Get the mutable reference to [`JsonValue`] corresponding to the query. If the value does not exist,
    /// it returns `None`.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    ///
    /// let mut v: JsonValue = "[-1, 0, 1]".parse().unwrap();
    ///
    /// if let Some(mut elem) = v.query_mut().child(1).find() {
    ///     if let Some(mut f) = elem.get_mut::<f64>() {
    ///         *f += 3.0;
    ///     }
    /// }
    /// assert_eq!(v.stringify().unwrap(), "[-1,3,1]");
    /// assert_eq!(v.query_mut().child(5).find(), None);
    /// ```
    pub fn find(self) -> Option<&'val mut JsonValue> {
        self.0
    }

    /// Get inner mutable reference to the `JsonValue` value corresponding to the query. This is similar to
    /// [`JsonValue::get_mut`]. It returns `None` when the value does not exist or type does not match.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    ///
    /// let mut v: JsonValue = "[-1, 0, 1]".parse().unwrap();
    ///
    /// // Get the second element 0.0
    /// if let Some(mut f) = v.query_mut().child(1).get::<f64>() {
    ///     *f += 3.0;
    /// }
    /// assert_eq!(v.stringify().unwrap(), "[-1,3,1]");
    ///
    /// // It's not a string value
    /// assert_eq!(v.query_mut().child(1).get::<String>(), None);
    /// // Index is out of bounds
    /// assert_eq!(v.query_mut().child(5).get::<f64>(), None);
    /// ```
    pub fn get<T: InnerAsRefMut>(self) -> Option<&'val mut T> {
        self.0.and_then(|v| v.get_mut())
    }
}

/// Trait to find nested elements of [`JsonValue`] value by some index. Since `usize` (for array) and `&str` (for object)
/// are already implementing this trait, basically you don't need to implement it by yourself.
///
/// Implementing this trait is useful when you want some custom index type or key type for JSON arrays and objects.
///
/// This is an example to access the element by negative index.
///
/// ```
/// use tinyjson::{ChildIndex, JsonQuery, JsonQueryMut, JsonValue};
///
/// struct SignedIdx(i32);
///
/// impl ChildIndex for SignedIdx {
///     fn index<'a>(self, q: &JsonQuery<'a>) -> JsonQuery<'a> {
///         if self.0 > 0 {
///             return (self.0 as usize).index(q);
///         }
///         let inner = if let Some(JsonValue::Array(arr)) = q.find() {
///             arr.get(arr.len().wrapping_sub((-self.0) as usize))
///         } else {
///             None
///         };
///         if let Some(v) = inner {
///             JsonQuery::new(v)
///         } else {
///             JsonQuery::default()
///         }
///     }
///     fn index_mut(self, q: JsonQueryMut<'_>) -> JsonQueryMut<'_> {
///         if self.0 > 0 {
///             return (self.0 as usize).index_mut(q);
///         }
///         let inner = if let Some(JsonValue::Array(arr)) = q.find() {
///             let idx = arr.len().wrapping_sub((-self.0) as usize);
///             arr.get_mut(idx)
///         } else {
///             None
///         };
///         if let Some(v) = inner {
///             JsonQueryMut::new(v)
///         } else {
///             JsonQueryMut::default()
///         }
///     }
/// }
///
/// let mut v: JsonValue = "[1, 2, 3, 4, 5]".parse().unwrap();
///
/// // Use `SignedIdx` with `JsonValue::query`
/// assert_eq!(v.query().child(SignedIdx(-1)).find(), Some(&JsonValue::Number(5.0)));
/// assert_eq!(v.query().child(SignedIdx(-100)).find(), None);
///
/// // Use `SignedIdx` with `JsonValue::query_mut`
/// assert_eq!(v.query_mut().child(SignedIdx(-1)).find(), Some(&mut JsonValue::Number(5.0)));
/// assert_eq!(v.query_mut().child(SignedIdx(-100)).find(), None);
/// ```
pub trait ChildIndex {
    /// Search elements of the `JsonValue` value by the index. This is used for [`JsonQuery`] to find elements by
    /// immutable reference.
    fn index<'a>(self, v: &JsonQuery<'a>) -> JsonQuery<'a>;
    /// Search elements of the `JsonValue` value by the index. This is used for [`JsonQueryMut`] to find elements by
    /// mutable reference.
    fn index_mut(self, v: JsonQueryMut<'_>) -> JsonQueryMut<'_>;
}

impl<'key> ChildIndex for &'key str {
    fn index<'a>(self, v: &JsonQuery<'a>) -> JsonQuery<'a> {
        let inner = if let Some(JsonValue::Object(obj)) = v.0 {
            obj.get(self)
        } else {
            None
        };
        JsonQuery(inner)
    }
    fn index_mut(self, v: JsonQueryMut<'_>) -> JsonQueryMut<'_> {
        let inner = if let Some(JsonValue::Object(obj)) = v.0 {
            obj.get_mut(self)
        } else {
            None
        };
        JsonQueryMut(inner)
    }
}

impl ChildIndex for usize {
    fn index<'a>(self, v: &JsonQuery<'a>) -> JsonQuery<'a> {
        let inner = if let Some(JsonValue::Array(arr)) = v.0 {
            arr.get(self)
        } else {
            None
        };
        JsonQuery(inner)
    }
    fn index_mut(self, v: JsonQueryMut<'_>) -> JsonQueryMut<'_> {
        let inner = if let Some(JsonValue::Array(arr)) = v.0 {
            arr.get_mut(self)
        } else {
            None
        };
        JsonQueryMut(inner)
    }
}

/// Serialization error. This error only happens when some write error happens on writing the serialized byte sequence
/// to the given `io::Write` object.
#[derive(Debug)]
pub struct JsonGenerateError {
    msg: String,
}

impl JsonGenerateError {
    pub fn message(&self) -> &str {
        self.msg.as_str()
    }
}

impl fmt::Display for JsonGenerateError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Generate error: {}", &self.msg)
    }
}

impl std::error::Error for JsonGenerateError {}

/// Convenient type alias for serialization results.
pub type JsonGenerateResult = Result<String, JsonGenerateError>;

/// JSON serializer for `JsonValue`.
///
/// Basically you don't need to use this struct directly since `JsonValue::stringify` or `JsonValue::format` methods are
/// using this internally.
///
/// ```
/// use tinyjson::{JsonGenerator, JsonValue};
///
/// let v = JsonValue::from("hello, world".to_string());
/// let mut buf = vec![];
/// let mut gen = JsonGenerator::new(&mut buf);
/// gen.generate(&v).unwrap();
///
/// assert_eq!(String::from_utf8(buf).unwrap(), "\"hello, world\"");
/// ```
pub struct JsonGenerator<'indent, W: Write> {
    out: W,
    indent: Option<&'indent str>,
}

impl<'indent, W: Write> JsonGenerator<'indent, W> {
    /// Create a new `JsonGenerator` object. The serialized byte sequence will be written to the given `io::Write`
    /// object.
    pub fn new(out: W) -> Self {
        Self { out, indent: None }
    }

    /// Set indent string. This will be used by [`JsonGenerator::generate`].
    /// ```
    /// use tinyjson::{JsonGenerator, JsonValue};
    ///
    /// let v = JsonValue::from(vec![1.0.into(), 2.0.into(), 3.0.into()]);
    /// let mut buf = vec![];
    /// let mut gen = JsonGenerator::new(&mut buf).indent("        ");
    /// gen.generate(&v).unwrap();
    ///
    /// assert_eq!(String::from_utf8(buf).unwrap(),
    /// "[
    ///         1,
    ///         2,
    ///         3
    /// ]");
    /// ```
    pub fn indent(mut self, indent: &'indent str) -> Self {
        self.indent = Some(indent);
        self
    }

    fn encode_string(&mut self, s: &str) -> io::Result<()> {
        const B: u8 = b'b'; // \x08
        const T: u8 = b't'; // \x09
        const N: u8 = b'n'; // \x0a
        const F: u8 = b'f'; // \x0c
        const R: u8 = b'r'; // \x0d
        const Q: u8 = b'"'; // \x22
        const S: u8 = b'\\'; // \x5c
        const U: u8 = 1; // non-printable

        #[rustfmt::skip]
        const ESCAPE_TABLE: [u8; 256] = [
         // 0  1  2  3  4  5  6  7  8  9  A  B  C  D  E  F
            U, U, U, U, U, U, U, U, B, T, N, U, F, R, U, U, // 0
            U, U, U, U, U, U, U, U, U, U, U, U, U, U, U, U, // 1
            0, 0, Q, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, // 2
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, // 3
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, // 4
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, S, 0, 0, 0, // 5
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, // 6
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, // 7
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, // 8
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, // 9
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, // A
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, // B
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, // C
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, // D
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, // E
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, // F
        ];

        self.out.write_all(b"\"")?;
        let mut start = 0;
        for (i, c) in s.char_indices() {
            let u = c as usize;
            if u < 256 {
                let esc = ESCAPE_TABLE[u];
                if esc == 0 {
                    continue;
                }
                if start != i {
                    self.out.write_all(s[start..i].as_bytes())?;
                }
                if esc == U {
                    write!(self.out, "\\u{:04x}", u)?;
                } else {
                    self.out.write_all(&[b'\\', esc])?;
                }
                start = i + 1;
            }
        }
        if start != s.len() {
            self.out.write_all(s[start..].as_bytes())?;
        }
        self.out.write_all(b"\"")
    }

    fn encode_number(&mut self, f: f64) -> io::Result<()> {
        if f.is_infinite() {
            Err(io::Error::new(
                io::ErrorKind::Other,
                "JSON cannot represent inf",
            ))
        } else if f.is_nan() {
            Err(io::Error::new(
                io::ErrorKind::Other,
                "JSON cannot represent NaN",
            ))
        } else {
            write!(self.out, "{}", f)
        }
    }

    fn encode_array(&mut self, array: &[JsonValue]) -> io::Result<()> {
        self.out.write_all(b"[")?;
        let mut first = true;
        for elem in array.iter() {
            if first {
                first = false;
            } else {
                self.out.write_all(b",")?;
            }
            self.encode(elem)?;
        }
        self.out.write_all(b"]")
    }

    fn encode_object(&mut self, m: &HashMap<String, JsonValue>) -> io::Result<()> {
        self.out.write_all(b"{")?;
        let mut first = true;
        for (k, v) in m {
            if first {
                first = false;
            } else {
                self.out.write_all(b",")?;
            }
            self.encode_string(k)?;
            self.out.write_all(b":")?;
            self.encode(v)?;
        }
        self.out.write_all(b"}")
    }

    fn encode(&mut self, value: &JsonValue) -> io::Result<()> {
        match value {
            JsonValue::Number(n) => self.encode_number(*n),
            JsonValue::Boolean(b) => self.out.write_all(if *b { b"true" } else { b"false" }),
            JsonValue::String(s) => self.encode_string(s),
            JsonValue::Null => self.out.write_all(b"null"),
            JsonValue::Array(a) => self.encode_array(a),
            JsonValue::Object(o) => self.encode_object(o),
        }
    }

    fn write_indent(&mut self, indent: &str, level: usize) -> io::Result<()> {
        for _ in 0..level {
            self.out.write_all(indent.as_bytes())?;
        }
        Ok(())
    }

    fn format_array(&mut self, array: &[JsonValue], indent: &str, level: usize) -> io::Result<()> {
        if array.is_empty() {
            return self.out.write_all(b"[]");
        }

        self.out.write_all(b"[\n")?;
        let mut first = true;
        for elem in array.iter() {
            if first {
                first = false;
            } else {
                self.out.write_all(b",\n")?;
            }
            self.write_indent(indent, level + 1)?;
            self.format(elem, indent, level + 1)?;
        }
        self.out.write_all(b"\n")?;
        self.write_indent(indent, level)?;
        self.out.write_all(b"]")
    }

    fn format_object(
        &mut self,
        m: &HashMap<String, JsonValue>,
        indent: &str,
        level: usize,
    ) -> io::Result<()> {
        if m.is_empty() {
            return self.out.write_all(b"{}");
        }

        self.out.write_all(b"{\n")?;
        let mut first = true;
        for (k, v) in m {
            if first {
                first = false;
            } else {
                self.out.write_all(b",\n")?;
            }
            self.write_indent(indent, level + 1)?;
            self.encode_string(k)?;
            self.out.write_all(b": ")?;
            self.format(v, indent, level + 1)?;
        }
        self.out.write_all(b"\n")?;
        self.write_indent(indent, level)?;
        self.out.write_all(b"}")
    }

    fn format(&mut self, value: &JsonValue, indent: &str, level: usize) -> io::Result<()> {
        match value {
            JsonValue::Number(n) => self.encode_number(*n),
            JsonValue::Boolean(b) => self.out.write_all(if *b { b"true" } else { b"false" }),
            JsonValue::String(s) => self.encode_string(s),
            JsonValue::Null => self.out.write_all(b"null"),
            JsonValue::Array(a) => self.format_array(a, indent, level),
            JsonValue::Object(o) => self.format_object(o, indent, level),
        }
    }

    /// Serialize the `JsonValue` into UTF-8 byte sequence. The result will be written to the `io::Write` object passed
    /// at [`JsonGenerator::new`].
    /// This method serializes the value without indentation by default. But after setting an indent string via
    /// [`JsonGenerator::indent`], this method will use the indent for elements of array and object.
    ///
    /// ```
    /// use tinyjson::{JsonGenerator, JsonValue};
    ///
    /// let v = JsonValue::from(vec![1.0.into(), 2.0.into(), 3.0.into()]);
    ///
    /// let mut buf = vec![];
    /// let mut gen = JsonGenerator::new(&mut buf);
    /// gen.generate(&v).unwrap();
    /// assert_eq!(String::from_utf8(buf).unwrap(), "[1,2,3]");
    ///
    /// let mut buf = vec![];
    /// let mut gen = JsonGenerator::new(&mut buf).indent("  "); // with 2-spaces indent
    /// gen.generate(&v).unwrap();
    ///
    /// assert_eq!(String::from_utf8(buf).unwrap(),
    /// "[
    ///   1,
    ///   2,
    ///   3
    /// ]");
    /// ```
    pub fn generate(&mut self, value: &JsonValue) -> io::Result<()> {
        if let Some(indent) = &self.indent {
            self.format(value, indent, 0)
        } else {
            self.encode(value)
        }
    }
}

/// Serialize the given `JsonValue` value to `String` without indentation. This method is almost identical to
/// `JsonValue::stringify` but exists for a historical reason.
///
/// ```
/// use tinyjson::JsonValue;
///
/// let v = JsonValue::from(vec![1.0.into(), 2.0.into(), 3.0.into()]);
/// let s = tinyjson::stringify(&v).unwrap();
/// assert_eq!(s, "[1,2,3]");
/// ```
pub fn stringify(value: &JsonValue) -> JsonGenerateResult {
    let mut to = Vec::new();
    let mut gen = JsonGenerator::new(&mut to);
    gen.generate(value).map_err(|err| JsonGenerateError {
        msg: format!("{}", err),
    })?;
    Ok(String::from_utf8(to).unwrap())
}

/// Serialize the given `JsonValue` value to `String` with 2-spaces indentation. This method is almost identical to
/// `JsonValue::format` but exists for a historical reason.
///
/// ```
/// use tinyjson::JsonValue;
///
/// let v = JsonValue::from(vec![1.0.into(), 2.0.into(), 3.0.into()]);
/// let s = tinyjson::format(&v).unwrap();
/// assert_eq!(s, "[\n  1,\n  2,\n  3\n]");
/// ```
pub fn format(value: &JsonValue) -> JsonGenerateResult {
    let mut to = Vec::new();
    let mut gen = JsonGenerator::new(&mut to).indent("  ");
    gen.generate(value).map_err(|err| JsonGenerateError {
        msg: format!("{}", err),
    })?;
    Ok(String::from_utf8(to).unwrap())
}

/// Parse error.
///
/// ```
/// use tinyjson::{JsonParser, JsonParseError};
/// let error = JsonParser::new("[1, 2, 3".chars()).parse().unwrap_err();
/// assert!(matches!(error, JsonParseError{..}));
/// ```
#[derive(Debug)]
pub struct JsonParseError {
    msg: String,
    line: usize,
    col: usize,
}

impl JsonParseError {
    fn new(msg: String, line: usize, col: usize) -> JsonParseError {
        JsonParseError { msg, line, col }
    }

    /// Get the line numbr where the parse error happened. This value is 1-based.
    ///
    /// ```
    /// use tinyjson::{JsonParser, JsonParseError};
    /// let error = JsonParser::new("[1, 2, 3".chars()).parse().unwrap_err();
    /// assert_eq!(error.line(), 1);
    /// ```
    pub fn line(&self) -> usize {
        self.line
    }

    /// Get the column numbr where the parse error happened. This value is 1-based.
    ///
    /// ```
    /// use tinyjson::{JsonParser, JsonParseError};
    /// let error = JsonParser::new("[1, 2, 3".chars()).parse().unwrap_err();
    /// assert_eq!(error.column(), 8);
    /// ```
    pub fn column(&self) -> usize {
        self.col
    }
}

impl fmt::Display for JsonParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "Parse error at line:{}, col:{}: {}",
            self.line, self.col, &self.msg,
        )
    }
}

impl std::error::Error for JsonParseError {}

/// Convenient type alias for parse results.
pub type JsonParseResult = Result<JsonValue, JsonParseError>;

// Note: char::is_ascii_whitespace is not available because some characters are not defined as
// whitespace character in JSON spec. For example, U+000C FORM FEED is whitespace in Rust but
// it isn't in JSON.
fn is_whitespace(c: char) -> bool {
    match c {
        '\u{0020}' | '\u{000a}' | '\u{000d}' | '\u{0009}' => true,
        _ => false,
    }
}

/// JSON parser to parse UTF-8 string into `JsonValue` value.
///
/// Basically you don't need to use this struct directly thanks to `FromStr` trait implementation.
///
/// ```
/// use tinyjson::{JsonParser, JsonValue};
///
/// let mut parser = JsonParser::new("[1, 2, 3]".chars());
/// let array = parser.parse().unwrap();
///
/// // Equivalent to the above code using `FromStr`
/// let array: JsonValue = "[1, 2, 3]".parse().unwrap();
/// ```
pub struct JsonParser<I>
where
    I: Iterator<Item = char>,
{
    chars: Peekable<I>,
    line: usize,
    col: usize,
}

impl<I: Iterator<Item = char>> JsonParser<I> {
    /// Create a new parser instance from an iterator which iterates characters. The iterator is usually built from
    /// `str::chars` for parsing `str` or `String` values.
    pub fn new(it: I) -> Self {
        JsonParser {
            chars: it.peekable(),
            line: 1,
            col: 0,
        }
    }

    fn err<T>(&self, msg: String) -> Result<T, JsonParseError> {
        Err(JsonParseError::new(msg, self.line, self.col))
    }

    fn unexpected_eof(&self) -> Result<char, JsonParseError> {
        Err(JsonParseError::new(
            String::from("Unexpected EOF"),
            self.line,
            self.col,
        ))
    }

    fn next_pos(&mut self, c: char) {
        if c == '\n' {
            self.col = 0;
            self.line += 1;
        } else {
            self.col += 1;
        }
    }

    fn peek(&mut self) -> Result<char, JsonParseError> {
        while let Some(c) = self.chars.peek().copied() {
            if !is_whitespace(c) {
                return Ok(c);
            }
            self.next_pos(c);
            self.chars.next().unwrap();
        }
        self.unexpected_eof()
    }

    fn next(&mut self) -> Option<char> {
        while let Some(c) = self.chars.next() {
            self.next_pos(c);
            if !is_whitespace(c) {
                return Some(c);
            }
        }
        None
    }

    fn consume(&mut self) -> Result<char, JsonParseError> {
        if let Some(c) = self.next() {
            Ok(c)
        } else {
            self.unexpected_eof()
        }
    }

    fn consume_no_skip(&mut self) -> Result<char, JsonParseError> {
        if let Some(c) = self.chars.next() {
            self.next_pos(c);
            Ok(c)
        } else {
            self.unexpected_eof()
        }
    }

    fn parse_object(&mut self) -> JsonParseResult {
        if self.consume()? != '{' {
            return self.err(String::from("Object must starts with '{'"));
        }

        if self.peek()? == '}' {
            self.consume().unwrap();
            return Ok(JsonValue::Object(HashMap::new()));
        }

        let mut m = HashMap::new();
        loop {
            let key = match self.parse_any()? {
                JsonValue::String(s) => s,
                v => return self.err(format!("Key of object must be string but found {:?}", v)),
            };

            let c = self.consume()?;
            if c != ':' {
                return self.err(format!(
                    "':' is expected after key of object but actually found '{}'",
                    c
                ));
            }

            m.insert(key, self.parse_any()?);

            match self.consume()? {
                ',' => {}
                '}' => return Ok(JsonValue::Object(m)),
                c => {
                    return self.err(format!(
                        "',' or '}}' is expected for object but actually found '{}'",
                        c.escape_debug(),
                    ))
                }
            }
        }
    }

    fn parse_array(&mut self) -> JsonParseResult {
        if self.consume()? != '[' {
            return self.err(String::from("Array must starts with '['"));
        }

        if self.peek()? == ']' {
            self.consume().unwrap();
            return Ok(JsonValue::Array(vec![]));
        }

        let mut v = vec![self.parse_any()?];
        loop {
            match self.consume()? {
                ',' => {}
                ']' => return Ok(JsonValue::Array(v)),
                c => {
                    return self.err(format!(
                        "',' or ']' is expected for array but actually found '{}'",
                        c
                    ))
                }
            }

            v.push(self.parse_any()?); // Next element
        }
    }

    fn push_utf16(&self, s: &mut String, utf16: &mut Vec<u16>) -> Result<(), JsonParseError> {
        if utf16.is_empty() {
            return Ok(());
        }

        match String::from_utf16(utf16) {
            Ok(utf8) => s.push_str(&utf8),
            Err(err) => return self.err(format!("Invalid UTF-16 sequence {:?}: {}", &utf16, err)),
        }
        utf16.clear();
        Ok(())
    }

    fn parse_string(&mut self) -> JsonParseResult {
        if self.consume()? != '"' {
            return self.err(String::from("String must starts with double quote"));
        }

        let mut utf16 = Vec::new(); // Buffer for parsing \uXXXX UTF-16 characters
        let mut s = String::new();
        loop {
            let c = match self.consume_no_skip()? {
                '\\' => match self.consume_no_skip()? {
                    '\\' => '\\',
                    '/' => '/',
                    '"' => '"',
                    'b' => '\u{0008}',
                    'f' => '\u{000c}',
                    'n' => '\n',
                    'r' => '\r',
                    't' => '\t',
                    'u' => {
                        let mut u = 0u16;
                        for _ in 0..4 {
                            let c = self.consume()?;
                            if let Some(h) = c.to_digit(16) {
                                u = u * 0x10 + h as u16;
                            } else {
                                return self.err(format!("Unicode character must be \\uXXXX (X is hex character) format but found character '{}'", c));
                            }
                        }
                        utf16.push(u);
                        // Additional \uXXXX character may follow. UTF-16 characters must be converted
                        // into UTF-8 string as sequence because surrogate pairs must be considered
                        // like "\uDBFF\uDFFF".
                        continue;
                    }
                    c => return self.err(format!("'\\{}' is invalid escaped character", c)),
                },
                '"' => {
                    self.push_utf16(&mut s, &mut utf16)?;
                    return Ok(JsonValue::String(s));
                }
                // Note: c.is_control() is not available here because JSON accepts 0x7f (DEL) in
                // string literals but 0x7f is control character.
                // Rough spec of JSON says string literal cannot contain control characters. But it
                // can actually contain 0x7f.
                c if (c as u32) < 0x20 => {
                    return self.err(format!(
                        "String cannot contain control character {}",
                        c.escape_debug(),
                    ));
                }
                c => c,
            };

            self.push_utf16(&mut s, &mut utf16)?;

            s.push(c);
        }
    }

    fn parse_constant(&mut self, s: &'static str) -> Option<JsonParseError> {
        for c in s.chars() {
            match self.consume_no_skip() {
                Ok(x) if x != c => {
                    let msg = format!(
                        "Unexpected character '{}' while parsing '{}' of {:?}",
                        x, c, s,
                    );
                    return Some(JsonParseError::new(msg, self.line, self.col));
                }
                Ok(_) => {}
                Err(e) => return Some(e),
            }
        }
        None
    }

    fn parse_null(&mut self) -> JsonParseResult {
        match self.parse_constant("null") {
            Some(err) => Err(err),
            None => Ok(JsonValue::Null),
        }
    }

    fn parse_true(&mut self) -> JsonParseResult {
        match self.parse_constant("true") {
            Some(err) => Err(err),
            None => Ok(JsonValue::Boolean(true)),
        }
    }

    fn parse_false(&mut self) -> JsonParseResult {
        match self.parse_constant("false") {
            Some(err) => Err(err),
            None => Ok(JsonValue::Boolean(false)),
        }
    }

    fn parse_number(&mut self) -> JsonParseResult {
        let mut s = String::new();

        if let Some('-') = self.chars.peek() {
            self.consume_no_skip().unwrap();
            s.push('-');
        };

        match self.consume_no_skip()? {
//            '0' => s.push('0'),
            d @ '0'..='9' => {
                s.push(d);
                while let Some('0'..='9') = self.chars.peek() {
                    s.push(self.consume_no_skip().unwrap());
                }
            }
            c => {
                let msg = format!("Expected '0'~'9' for integer part of number but got {}", c);
                return self.err(msg);
            }
        }

        if let Some('.') = self.chars.peek() {
            s.push(self.consume_no_skip().unwrap()); // Eat '.'

            match self.consume_no_skip()? {
                d @ '0'..='9' => s.push(d),
                c => {
                    let msg = format!("At least one digit must follow after '.' but got {}", c);
                    return self.err(msg);
                }
            }

            while let Some('0'..='9') = self.chars.peek() {
                s.push(self.consume_no_skip().unwrap());
            }
        }

        if let Some('e' | 'E') = self.chars.peek() {
            s.push(self.consume_no_skip().unwrap()); // Eat 'e' or 'E'

            if let Some('-' | '+') = self.chars.peek() {
                s.push(self.consume_no_skip().unwrap());
            }

            match self.consume_no_skip()? {
                d @ '0'..='9' => s.push(d),
                c => {
                    return self.err(format!(
                        "At least one digit must follow exponent part of number but got {}",
                        c
                    ));
                }
            };

            while let Some('0'..='9') = self.chars.peek() {
                s.push(self.consume_no_skip().unwrap());
            }
        }

        match s.parse() {
            Ok(n) => Ok(JsonValue::Number(n)),
            Err(err) => self.err(format!("Invalid number literal '{}': {}", s, err)),
        }
    }

    fn parse_any(&mut self) -> JsonParseResult {
        match self.peek()? {
            '0'..='9' | '-' => self.parse_number(),
            '"' => self.parse_string(),
            '[' => self.parse_array(),
            '{' => self.parse_object(),
            't' => self.parse_true(),
            'f' => self.parse_false(),
            'n' => self.parse_null(),
            c => self.err(format!("Invalid character: {}", c.escape_debug())),
        }
    }

    /// Run the parser to parse one JSON value.
    pub fn parse(&mut self) -> JsonParseResult {
        let v = self.parse_any()?;

        if let Some(c) = self.next() {
            return self.err(format!(
                "Expected EOF but got character '{}'",
                c.escape_debug(),
            ));
        }

        Ok(v)
    }
}

/// Parse given `str` object into `JsonValue` value. This is recommended way to parse strings into JSON value with
/// this library.
///
/// ```
/// use tinyjson::JsonValue;
///
/// let array: JsonValue = "[1, 2, 3]".parse().unwrap();
/// assert!(array.is_array());
/// ```
impl FromStr for JsonValue {
    type Err = JsonParseError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        JsonParser::new(s.chars()).parse()
    }
}

/// Enum to represent one JSON value. Each variant represents corresponding JSON types.
/// ```
/// use tinyjson::JsonValue;
/// use std::convert::TryInto;
///
/// // Convert from raw values using `From` trait
/// let value = JsonValue::from("this is string".to_string());
///
/// // Get reference to inner value
/// let maybe_number: Option<&f64> = value.get();
/// assert!(maybe_number.is_none());
/// let maybe_string: Option<&String> = value.get();
/// assert!(maybe_string.is_some());
///
/// // Check type of JSON value
/// assert!(matches!(value, JsonValue::String(_)));
/// assert!(value.is_string());
///
/// // Convert into raw values using `TryInto` trait
/// let original_value: String = value.try_into().unwrap();
/// ```
#[derive(Debug, Clone, PartialEq)]
pub enum JsonValue {
    /// Number type value.
    Number(f64),
    /// Boolean type value.
    Boolean(bool),
    /// String type value.
    String(String),
    /// Null type value.
    Null,
    /// Array type value.
    Array(Vec<JsonValue>),
    /// Object type value.
    Object(HashMap<String, JsonValue>),
}

/// Trait to access to inner value of `JsonValue` as reference.
///
/// This is used by several APIs like [`JsonValue::get`] to represent any inner values of [`JsonValue`].
pub trait InnerAsRef {
    fn json_value_as(v: &JsonValue) -> Option<&Self>;
}

macro_rules! impl_inner_ref {
    ($to:ty, $pat:pat => $val:expr) => {
        impl InnerAsRef for $to {
            fn json_value_as(v: &JsonValue) -> Option<&$to> {
                use JsonValue::*;
                match v {
                    $pat => Some($val),
                    _ => None,
                }
            }
        }
    };
}

impl_inner_ref!(f64, Number(n) => n);
impl_inner_ref!(bool, Boolean(b) => b);
impl_inner_ref!(String, String(s) => s);
impl_inner_ref!((), Null => &NULL);
impl_inner_ref!(Vec<JsonValue>, Array(a) => a);
impl_inner_ref!(HashMap<String, JsonValue>, Object(h) => h);

/// Trait to access to inner value of `JsonValue` as mutable reference.
///
/// This is a mutable version of [`InnerAsRef`].
pub trait InnerAsRefMut {
    fn json_value_as_mut(v: &mut JsonValue) -> Option<&mut Self>;
}

macro_rules! impl_inner_ref_mut {
    ($to:ty, $pat:pat => $val:expr) => {
        impl InnerAsRefMut for $to {
            fn json_value_as_mut(v: &mut JsonValue) -> Option<&mut $to> {
                use JsonValue::*;
                match v {
                    $pat => Some($val),
                    _ => None,
                }
            }
        }
    };
}

impl_inner_ref_mut!(f64, Number(n) => n);
impl_inner_ref_mut!(bool, Boolean(b) => b);
impl_inner_ref_mut!(String, String(s) => s);
impl_inner_ref_mut!(Vec<JsonValue>, Array(a) => a);
impl_inner_ref_mut!(HashMap<String, JsonValue>, Object(h) => h);

// Note: matches! is available from Rust 1.42
macro_rules! is_xxx {
    (
        $(#[$meta:meta])*
        $name:ident,
        $variant:pat,
    ) => {
        $(#[$meta])*
        pub fn $name(&self) -> bool {
            match self {
                $variant => true,
                _ => false,
            }
        }
    };
}

impl JsonValue {
    /// Get immutable reference to the inner value.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    ///
    /// let value: JsonValue = "[1, 2, 3]".parse().unwrap();
    /// let vec: &Vec<_> = value.get().unwrap();
    /// assert_eq!(vec[0], JsonValue::from(1.0));
    ///
    /// // Try to convert with incorrect type
    /// assert!(value.get::<f64>().is_none());
    /// ```
    pub fn get<T: InnerAsRef>(&self) -> Option<&T> {
        T::json_value_as(self)
    }

    /// Get mutable reference to the inner value.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    ///
    /// let mut value: JsonValue = "[1, 2, 3]".parse().unwrap();
    /// let vec: &mut Vec<_> = value.get_mut().unwrap();
    /// vec[0] = JsonValue::from(false);
    /// assert_eq!(value.stringify().unwrap(), "[false,2,3]");
    ///
    /// // Try to convert with incorrect type
    /// assert!(value.get_mut::<f64>().is_none());
    /// ```
    pub fn get_mut<T: InnerAsRefMut>(&mut self) -> Option<&mut T> {
        T::json_value_as_mut(self)
    }

    is_xxx!(
        /// Check if the inner value is a boolean.
        ///
        /// ```
        /// use tinyjson::JsonValue;
        ///
        /// let v = JsonValue::from(true);
        /// assert!(v.is_bool());
        /// let v = JsonValue::from(1.0);
        /// assert!(!v.is_bool());
        /// ```
        is_bool,
        JsonValue::Boolean(_),
    );
    is_xxx!(
        /// Check if the inner value is a number. Note that [`matches!`] macro may fit better to your use case since it
        /// allows to write `if` guard if you use Rust 1.42.0 or later.
        ///
        /// ```
        /// use tinyjson::JsonValue;
        ///
        /// let v = JsonValue::from(1.0);
        /// assert!(v.is_number());
        /// let v = JsonValue::from(false);
        /// assert!(!v.is_number());
        ///
        /// // matches! macro may be better choice
        /// let v = JsonValue::from(-1.0);
        /// assert!(matches!(&v, JsonValue::Number(n) if *n < 0.0));
        /// ```
        is_number,
        JsonValue::Number(_),
    );
    is_xxx!(
        /// Check if the inner value is a string. Note that [`matches!`] macro may fit better to your use case since it
        /// allows to write `if` guard if you use Rust 1.42.0 or later.
        ///
        /// ```
        /// use tinyjson::JsonValue;
        ///
        /// let v = JsonValue::from("foo".to_string());
        /// assert!(v.is_string());
        /// let v = JsonValue::from(1.0);
        /// assert!(!v.is_string());
        ///
        /// // matches! macro may be better choice
        /// let v = JsonValue::from("!".to_string());
        /// assert!(matches!(&v, JsonValue::String(s) if !s.is_empty()));
        /// ```
        is_string,
        JsonValue::String(_),
    );
    is_xxx!(
        /// Check if the inner value is null.
        ///
        /// ```
        /// use tinyjson::JsonValue;
        ///
        /// let v = JsonValue::from(()); // () is inner representation of null value
        /// assert!(v.is_null());
        /// let v = JsonValue::from(false);
        /// assert!(!v.is_null());
        /// ```
        is_null,
        JsonValue::Null,
    );
    is_xxx!(
        /// Check if the inner value is an array. Note that [`matches!`] macro may fit better to your use case since it
        /// allows to write `if` guard if you use Rust 1.42.0 or later.
        ///
        /// ```
        /// use tinyjson::JsonValue;
        ///
        /// let v = JsonValue::from(vec![]);
        /// assert!(v.is_array());
        /// let v = JsonValue::from(1.0);
        /// assert!(!v.is_array());
        ///
        /// // matches! macro may be better choice
        /// let v = JsonValue::from(vec![1.0.into()]);
        /// assert!(matches!(&v, JsonValue::Array(a) if !a.is_empty()));
        /// ```
        is_array,
        JsonValue::Array(_),
    );
    is_xxx!(
        /// Check if the inner value is an object. Note that [`matches!`] macro may fit better to your use case since it
        /// allows to write `if` guard if you use Rust 1.42.0 or later.
        ///
        /// ```
        /// use tinyjson::JsonValue;
        /// use std::collections::HashMap;
        ///
        /// let v = JsonValue::from(HashMap::new());
        /// assert!(v.is_object());
        /// let v = JsonValue::from(vec![]);
        /// assert!(!v.is_object());
        ///
        /// // matches! macro may be better choice
        /// let mut m = HashMap::new();
        /// m.insert("hello".to_string(), "world".to_string().into());
        /// let v = JsonValue::from(m);
        /// assert!(matches!(&v, JsonValue::Object(o) if o.contains_key("hello")));
        /// assert!(!matches!(&v, JsonValue::Object(o) if o.contains_key("goodbye")));
        /// ```
        is_object,
        JsonValue::Object(_),
    );

    /// Convert this JSON value to `String` value.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    ///
    /// let v = JsonValue::from(vec![1.0.into(), true.into(), "str".to_string().into()]);
    /// let s = v.stringify().unwrap();
    /// assert_eq!(&s, "[1,true,\"str\"]");
    /// ```
    pub fn stringify(&self) -> JsonGenerateResult {
        stringify(self)
    }

    /// Write this JSON value to the given `io::Write` object as UTF-8 byte sequence.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    /// use std::io::Write;
    ///
    /// let v = JsonValue::from(vec![1.0.into(), true.into(), "str".to_string().into()]);
    /// let mut bytes = vec![];
    /// v.write_to(&mut bytes).unwrap();
    /// assert_eq!(&String::from_utf8(bytes).unwrap(), "[1,true,\"str\"]");
    /// ```
    pub fn write_to<W: io::Write>(&self, w: &mut W) -> io::Result<()> {
        JsonGenerator::new(w).generate(self)
    }

    /// Convert this JSON value to `String` value with 2-spaces indentation.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    ///
    /// let v = JsonValue::from(vec![1.0.into(), true.into(), "str".to_string().into()]);
    /// let s = v.format().unwrap();
    /// assert_eq!(&s,
    /// "[
    ///   1,
    ///   true,
    ///   \"str\"
    /// ]");
    /// ```
    pub fn format(&self) -> JsonGenerateResult {
        format(self)
    }

    /// Write this JSON value to the given `io::Write` object as UTF-8 byte sequence with 2-spaces indentation.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    ///
    /// let v = JsonValue::from(vec![1.0.into(), true.into(), "str".to_string().into()]);
    /// let mut bytes = vec![];
    /// v.format_to(&mut bytes).unwrap();
    /// assert_eq!(&String::from_utf8(bytes).unwrap(),
    /// "[
    ///   1,
    ///   true,
    ///   \"str\"
    /// ]");
    /// ```
    pub fn format_to<W: io::Write>(&self, w: &mut W) -> io::Result<()> {
        JsonGenerator::new(w).indent("  ").generate(self)
    }

    /// Create a panic-safe JSON query for this value. It allows accessing the nested values by index/key/value
    /// easily via immutable reference.
    ///
    /// - `.child()` for accessing its array or object elements by index or key
    /// - `.child_by()` for accessing its array or object elements by a value predicate
    ///
    /// See [`JsonQuery`] for more details.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    ///
    /// // Find some nested element
    /// let v: JsonValue = r#"[{"foo": [false, true]}]"#.parse().unwrap();
    /// let found = v.query().child(0).child("foo").child(1).find();
    /// assert_eq!(found, Some(&JsonValue::from(true)));
    ///
    /// // Check if key or index exsits
    /// assert!(v.query().child(0).child("foo").exists());
    /// assert!(!v.query().child(1).exists());
    /// assert!(!v.query().child("bar").exists());
    ///
    /// // Access nested inner value directly
    /// let v: JsonValue = r#"[{"foo": ["first", "second"]}]"#.parse().unwrap();
    /// let s: &String = v.query().child(0).child("foo").child(1).get().unwrap();
    /// assert_eq!(s, "second");
    /// ```
    pub fn query(&self) -> JsonQuery<'_> {
        JsonQuery::new(self)
    }

    /// Create a panic-safe JSON query for this value. It allows modifying the nested values by index/key/value
    /// easily via mutable reference.
    ///
    /// - `.child()` for accessing its array or object elements by index or key
    /// - `.child_by()` for accessing its array or object elements by a value predicate
    ///
    /// See [`JsonQueryMut`] for more details.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    ///
    /// // Modify nested JsonValue element
    /// let mut v: JsonValue = r#"[{"foo": [true]}]"#.parse().unwrap();
    /// if let Some(found) = v.query_mut().child(0).child("foo").child(0).find() {
    ///     *found = JsonValue::Number(10.0);
    /// }
    /// assert_eq!(v.stringify().unwrap(), r#"[{"foo":[10]}]"#);
    ///
    /// // Modify nested inner value
    /// let mut v: JsonValue = r#"[{"foo": ["hello"]}]"#.parse().unwrap();
    /// if let Some(s) = v.query_mut().child(0).child("foo").child(0).get::<String>() {
    ///     s.push_str(", world!");
    /// }
    /// assert_eq!(v.stringify().unwrap(), r#"[{"foo":["hello, world!"]}]"#);
    /// ```
    pub fn query_mut(&mut self) -> JsonQueryMut<'_> {
        JsonQueryMut::new(self)
    }
}

/// Access the element value of the key of object.
///
/// ```
/// use tinyjson::JsonValue;
/// use std::collections::HashMap;
///
/// let mut m = HashMap::new();
/// m.insert("foo".to_string(), 1.0.into());
/// let v = JsonValue::from(m);
/// let i = &v["foo"];
/// assert_eq!(i, &JsonValue::Number(1.0));
/// ```
///
/// Like standard containers such as `Vec` or `HashMap`, it will panic when the given `JsonValue` value is not an object
///
/// ```should_panic
/// # use tinyjson::JsonValue;
/// let v = JsonValue::from(vec![]);
/// let _ = &v["foo"]; // Panic
/// ```
///
/// or when the key does not exist in the object.
///
/// ```should_panic
/// # use tinyjson::JsonValue;
/// # use std::collections::HashMap;
/// let v = JsonValue::from(HashMap::new());
/// let _ = &v["foo"]; // Panic
/// ```
///
/// Using this operator, you can access the nested elements quickly
///
/// ```
/// # use tinyjson::JsonValue;
/// let mut json: JsonValue = r#"
/// {
///   "foo": {
///     "bar": [
///       { "target": 42 }
///     ]
///   }
/// }
/// "#.parse().unwrap();
///
/// // Access with index operator
/// let target_value: f64 = *json["foo"]["bar"][0]["target"].get().unwrap();
/// assert_eq!(target_value, 42.0);
/// ```
impl<'a> Index<&'a str> for JsonValue {
    type Output = JsonValue;

    fn index(&self, key: &'a str) -> &Self::Output {
        let obj = match self {
            JsonValue::Object(o) => o,
            _ => panic!(
                "Attempted to access to an object with key '{}' but actually it was {:?}",
                key, self
            ),
        };

        match obj.get(key) {
            Some(json) => json,
            None => panic!("Key '{}' was not found in {:?}", key, self),
        }
    }
}

/// Access the element value of the index of array.
///
/// ```
/// use tinyjson::JsonValue;
///
/// let v = JsonValue::from(vec![1.0.into(), true.into()]);
/// let b = &v[1];
/// assert_eq!(b, &JsonValue::Boolean(true));
/// ```
///
/// Like standard containers such as `Vec` or `HashMap`, it will panic when the given `JsonValue` value is not an array
///
/// ```should_panic
/// # use tinyjson::JsonValue;
/// use std::collections::HashMap;
/// let v = JsonValue::from(HashMap::new());
/// let _ = &v[0]; // Panic
/// ```
///
/// or when the index is out of bounds.
///
/// ```should_panic
/// # use tinyjson::JsonValue;
/// let v = JsonValue::from(vec![]);
/// let _ = &v[0]; // Panic
/// ```
impl Index<usize> for JsonValue {
    type Output = JsonValue;

    fn index(&self, index: usize) -> &'_ Self::Output {
        let array = match self {
            JsonValue::Array(a) => a,
            _ => panic!(
                "Attempted to access to an array with index {} but actually the value was {:?}",
                index, self,
            ),
        };
        &array[index]
    }
}

/// Access the element value of the key of mutable object.
///
/// ```
/// use tinyjson::JsonValue;
/// use std::collections::HashMap;
///
/// let mut m = HashMap::new();
/// m.insert("foo".to_string(), 1.0.into());
/// let mut v = JsonValue::from(m);
/// v["foo"] = JsonValue::Number(3.14);
/// assert_eq!(v["foo"], JsonValue::Number(3.14));
/// ```
///
/// Like standard containers such as `Vec` or `HashMap`, it will panic when the given `JsonValue` value is not an object
///
/// ```should_panic
/// # use tinyjson::JsonValue;
/// let mut v = JsonValue::from(vec![]);
/// let _ = &mut v["foo"]; // Panic
/// ```
///
/// or when the key does not exist in the object.
///
/// ```should_panic
/// # use tinyjson::JsonValue;
/// # use std::collections::HashMap;
/// let mut v = JsonValue::from(HashMap::new());
/// let _ = &mut v["foo"]; // Panic
/// ```
///
/// Using this operator, you can modify the nested elements quickly
///
/// ```
/// # use tinyjson::JsonValue;
/// let mut json: JsonValue = r#"
/// {
///   "foo": {
///     "bar": [
///       { "target": 42 }
///     ]
///   }
/// }
/// "#.parse().unwrap();
///
/// // Modify with index operator
/// json["foo"]["bar"][0]["target"] = JsonValue::Boolean(false);
/// assert_eq!(json["foo"]["bar"][0]["target"], JsonValue::Boolean(false));
/// ```
impl<'a> IndexMut<&'a str> for JsonValue {
    fn index_mut(&mut self, key: &'a str) -> &mut Self::Output {
        let obj = match self {
            JsonValue::Object(o) => o,
            _ => panic!(
                "Attempted to access to an object with key '{}' but actually it was {:?}",
                key, self
            ),
        };

        if let Some(json) = obj.get_mut(key) {
            json
        } else {
            panic!("Key '{}' was not found in object", key)
        }
    }
}

/// Access the element value of the index of mutable array.
///
/// ```
/// use tinyjson::JsonValue;
///
/// let mut v = JsonValue::from(vec![1.0.into(), true.into()]);
/// let b = &mut v[1];
/// assert_eq!(b, &JsonValue::Boolean(true));
/// ```
///
/// Like standard containers such as `Vec` or `HashMap`, it will panic when the given `JsonValue` value is not an array
///
/// ```should_panic
/// # use tinyjson::JsonValue;
/// use std::collections::HashMap;
/// let mut v = JsonValue::from(HashMap::new());
/// let _ = &mut v[0]; // Panic
/// ```
///
/// or when the index is out of bounds.
///
/// ```should_panic
/// # use tinyjson::JsonValue;
/// let mut v = JsonValue::from(vec![]);
/// let _ = &mut v[0]; // Panic
/// ```
impl IndexMut<usize> for JsonValue {
    fn index_mut(&mut self, index: usize) -> &mut Self::Output {
        let array = match self {
            JsonValue::Array(a) => a,
            _ => panic!(
                "Attempted to access to an array with index {} but actually the value was {:?}",
                index, self,
            ),
        };

        &mut array[index]
    }
}

macro_rules! impl_from {
    (
        $(#[$meta:meta])*
        $v:ident: $t:ty => $e:expr
    ) => {
        $(#[$meta])*
        impl From<$t> for JsonValue {
            fn from($v: $t) -> JsonValue {
                use JsonValue::*;
                $e
            }
        }
    };
}

impl_from!(
    /// Convert `f64` value into `JsonValue`.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    /// let v = JsonValue::from(1.0);
    /// assert!(v.is_number());
    /// ```
    n: f64 => Number(n)
);
impl_from!(
    /// Convert `bool` value into `JsonValue`.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    /// let v = JsonValue::from(true);
    /// assert!(v.is_bool());
    /// ```
    b: bool => Boolean(b)
);
impl_from!(
    /// Convert `bool` value into `JsonValue`. Note that `&str` is not available. Explicitly allocate `String` object
    /// and pass it.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    /// let v = JsonValue::from("foo".to_string());
    /// assert!(v.is_string());
    /// ```
    s: String => String(s)
);
impl_from!(
    /// Convert `()` into `JsonValue`. `()` is an inner representation of null JSON value.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    /// let v = JsonValue::from(());
    /// assert!(v.is_null());
    /// ```
    _x: () => Null
);
impl_from!(
    /// Convert `Vec` value into `JsonValue`.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    /// let v = JsonValue::from(vec![1.0.into(), true.into()]);
    /// assert!(v.is_array());
    /// ```
    a: Vec<JsonValue> => Array(a)
);
impl_from!(
    /// Convert `HashMap` value into `JsonValue`.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    /// use std::collections::HashMap;
    /// let mut m = HashMap::new();
    /// m.insert("foo".to_string(), 1.0.into());
    /// let v = JsonValue::from(m);
    /// assert!(v.is_object());
    /// ```
    o: HashMap<String, JsonValue> => Object(o)
);

/// Error caused when trying to convert `JsonValue` into some wrong type value.
///
/// ```
/// use tinyjson::{JsonValue, UnexpectedValue};
/// use std::convert::TryFrom;
///
/// let error = String::try_from(JsonValue::from(1.0)).unwrap_err();
/// assert!(matches!(error, UnexpectedValue{..}));
/// ```
#[derive(Debug)]
pub struct UnexpectedValue {
    value: JsonValue,
    expected: &'static str,
}

impl UnexpectedValue {
    /// Get reference to the value which failed to be converted.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    /// use std::convert::TryFrom;
    ///
    /// let error = String::try_from(JsonValue::from(1.0)).unwrap_err();
    /// assert_eq!(error.value(), &JsonValue::Number(1.0));
    /// ```
    pub fn value(&self) -> &JsonValue {
        &self.value
    }
}

impl fmt::Display for UnexpectedValue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "Unexpected JSON value: {:?}. Expected {} value",
            self.value, self.expected
        )
    }
}

impl std::error::Error for UnexpectedValue {}

/// Convert this error into the value which failed to be converted.
///
/// ```
/// use tinyjson::JsonValue;
/// use std::convert::TryFrom;
///
/// let error = String::try_from(JsonValue::from(1.0)).unwrap_err();
/// assert_eq!(JsonValue::from(error), JsonValue::Number(1.0));
/// ```
impl From<UnexpectedValue> for JsonValue {
    fn from(err: UnexpectedValue) -> Self {
        err.value
    }
}

macro_rules! impl_try_from {
    (
        $(#[$meta:meta])*
        $pat:pat => $val:expr,
        $ty:ty,
    ) => {
        $(#[$meta])*
        impl TryFrom<JsonValue> for $ty {
            type Error = UnexpectedValue;

            fn try_from(v: JsonValue) -> Result<Self, UnexpectedValue> {
                match v {
                    $pat => Ok($val),
                    v => Err(UnexpectedValue {
                        value: v,
                        expected: stringify!($ty),
                    }),
                }
            }
        }
    };
}

impl_try_from!(
    /// Try to convert the `JsonValue` value into `f64`. `UnexpectedValue` error happens when trying to convert an
    /// incorrect type value.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    /// use std::convert::TryFrom;
    ///
    /// let v = JsonValue::from(1.0);
    /// let r = f64::try_from(v);
    /// assert!(r.is_ok());
    ///
    /// let v = JsonValue::from(true);
    /// let r = f64::try_from(v);
    /// assert!(r.is_err());
    /// ```
    JsonValue::Number(n) => n,
    f64,
);
impl_try_from!(
    /// Try to convert the `JsonValue` value into `bool`. `UnexpectedValue` error happens when trying to convert an
    /// incorrect type value.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    /// use std::convert::TryFrom;
    ///
    /// let v = JsonValue::from(true);
    /// let r = bool::try_from(v);
    /// assert!(r.is_ok());
    ///
    /// let v = JsonValue::from(1.0);
    /// let r = bool::try_from(v);
    /// assert!(r.is_err());
    /// ```
    JsonValue::Boolean(b) => b,
    bool,
);
impl_try_from!(
    /// Try to convert the `JsonValue` value into `String`. `UnexpectedValue` error happens when trying to convert an
    /// incorrect type value.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    /// use std::convert::TryFrom;
    ///
    /// let v = JsonValue::from("foo".to_string());
    /// let r = String::try_from(v);
    /// assert!(r.is_ok());
    ///
    /// let v = JsonValue::from(1.0);
    /// let r = String::try_from(v);
    /// assert!(r.is_err());
    /// ```
    JsonValue::String(s) => s,
    String,
);
impl_try_from!(
    /// Try to convert the `JsonValue` value into `()`. Note that `()` is an inner representation of null JSON value.
    /// `UnexpectedValue` error happens when trying to convert an incorrect type value.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    /// use std::convert::TryFrom;
    ///
    /// let v = JsonValue::from(());
    /// let r = <()>::try_from(v);
    /// assert!(r.is_ok());
    ///
    /// let v = JsonValue::from(1.0);
    /// let r = <()>::try_from(v);
    /// assert!(r.is_err());
    /// ```
    JsonValue::Null => (),
    (),
);
impl_try_from!(
    /// Try to convert the `JsonValue` value into `Vec<JsonValue>`. `UnexpectedValue` error happens when trying to
    /// convert an incorrect type value.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    /// use std::convert::TryFrom;
    ///
    /// let v = JsonValue::from(vec![true.into()]);
    /// let r = <Vec<_>>::try_from(v);
    /// assert!(r.is_ok());
    ///
    /// let v = JsonValue::from(1.0);
    /// let r = <Vec<_>>::try_from(v);
    /// assert!(r.is_err());
    /// ```
    JsonValue::Array(a) => a,
    Vec<JsonValue>,
);
impl_try_from!(
    /// Try to convert the `JsonValue` value into `HashMap<String, JsonValue>`. `UnexpectedValue` error happens when
    /// trying to convert an incorrect type value.
    ///
    /// ```
    /// use tinyjson::JsonValue;
    /// use std::convert::TryFrom;
    /// use std::collections::HashMap;
    ///
    /// let mut m = HashMap::new();
    /// m.insert("foo".to_string(), 42.0.into());
    /// let v = JsonValue::from(m);
    /// let r = <HashMap<_, _>>::try_from(v);
    /// assert!(r.is_ok());
    ///
    /// let v = JsonValue::from(1.0);
    /// let r = <HashMap<_, _>>::try_from(v);
    /// assert!(r.is_err());
    /// ```
    JsonValue::Object(o) => o,
    HashMap<String, JsonValue>,
);

fn untyped_example(data: &str) -> String {
    // Some JSON input data as a &str. Maybe this comes from the user.

    // Parse the string of data into serde_json::Value.
    let parsed =  JsonValue::from_str(data);
    match parsed {
        Ok(v) => v.stringify().unwrap(),
        Err(e) => panic!("error parsing string: {:?}", e),
    }

}


use std::env;
use std::fs;
use std::io::{Read};


fn main() {
    let args: Vec<String> = env::args().collect();

    let input_string = if args.len() > 1 {
        let filename = &args[1];
        match fs::read_to_string(filename) {
            Ok(content) => content,
            Err(error) => {
                eprintln!("Error reading file: {}", error);
                return;
            }
        }
    } else {
        let mut input_string = String::new();
        match io::stdin().read_to_string(&mut input_string) {
            Ok(_) => (),
            Err(error) => {
                eprintln!("Error reading from stdin: {}", error);
                return;
            }
        }
        input_string
    };

    // Process the input_string here (you can print it as an example)
    println!("Input string: {}", input_string);
    let res: String = untyped_example(&input_string);
    println!("Parsed Value: {:?}", res)

}