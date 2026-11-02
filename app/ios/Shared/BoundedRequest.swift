import Foundation

/// Bound response bytes, disallow redirects (never forward capabilities), no cache/cookies.
final class BoundedRequest: NSObject, URLSessionDataDelegate {
  private var session: URLSession?
  private var task: URLSessionDataTask?
  private var data = Data(), code = 0
  private let limit:Int
  private var complete: ((Int,Data?)->Void)?
  init(_ request:URLRequest,limit:Int,complete:@escaping(Int,Data?)->Void) {
    self.limit = limit; self.complete = complete; super.init()
    let config = URLSessionConfiguration.ephemeral; config.urlCache = nil; config.httpCookieStorage = nil; config.requestCachePolicy = .reloadIgnoringLocalCacheData; config.timeoutIntervalForResource = 8
    // URLSession retains its delegate until invalidation: fire-and-forget requests
    // remain alive through didCompleteWithError, which breaks the ownership cycle.
    session = URLSession(configuration:config,delegate:self,delegateQueue:nil)
    task = session?.dataTask(with:request); task?.resume()
  }
  func cancel() { task?.cancel(); session?.invalidateAndCancel() }
  func urlSession(_ session:URLSession,dataTask:URLSessionDataTask,didReceive response:URLResponse,completionHandler:@escaping(URLSession.ResponseDisposition)->Void) {
    code = (response as? HTTPURLResponse)?.statusCode ?? 0
    completionHandler(response.expectedContentLength > Int64(limit) ? .cancel : .allow)
  }
  func urlSession(_ session:URLSession,dataTask:URLSessionDataTask,didReceive chunk:Data) { if data.count + chunk.count > limit { cancel() } else { data.append(chunk) } }
  func urlSession(_ session:URLSession,task:URLSessionTask,willPerformHTTPRedirection response:HTTPURLResponse,newRequest request:URLRequest,completionHandler:@escaping(URLRequest?)->Void) { completionHandler(nil) }
  func urlSession(_ session:URLSession,task:URLSessionTask,didCompleteWithError error:Error?) { let callback = complete; complete = nil; callback?(error == nil ? code : 0,error == nil ? data : nil); session.finishTasksAndInvalidate(); self.session = nil; self.task = nil }
}
